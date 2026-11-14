"""Reproducible FIRMS JSON -> SQLite. Originals are registered by SHA-256."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import min_weight_full_bipartite_matching
from shapely.geometry import shape
from shapely import intersects_xy

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data/firewatch.sqlite"
CONFIG = {"id":"center-1km-30min-v1", "max_distance_km":1, "max_time_min":30,
          "matched":0.7,"possible":0.45,"formula":"0.6 * distance_score + 0.4 * time_score",
          "grouping":"maximum-weight one-to-one assignment; unmatched retained",
          "footprint":"unavailable: scan/track retained but orientation not provided"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS source_files(id TEXT PRIMARY KEY,filename TEXT,checksum TEXT,rows INTEGER,ingested TEXT);
CREATE TABLE IF NOT EXISTS observations(id TEXT PRIMARY KEY,file_id TEXT,row_number INTEGER,sensor TEXT,satellite TEXT,
 year INTEGER,month INTEGER,date TEXT,time TEXT,ts REAL,lat REAL,lon REAL,confidence TEXT,frp REAL,brightness REAL,
 scan REAL,track REAL,daynight TEXT,product TEXT,region TEXT,type INTEGER,eligible INTEGER,
 status TEXT,group_id TEXT,raw_json TEXT);
CREATE INDEX IF NOT EXISTS obs_filter ON observations(year,month,region,daynight,sensor);
CREATE INDEX IF NOT EXISTS obs_time ON observations(ts);
CREATE INDEX IF NOT EXISTS obs_date ON observations(date,region,daynight);
CREATE INDEX IF NOT EXISTS obs_location ON observations(lat,lon);
CREATE TABLE IF NOT EXISTS rejected(file_id TEXT,row_number INTEGER,reason TEXT,raw_json TEXT,PRIMARY KEY(file_id,row_number));
CREATE TABLE IF NOT EXISTS candidate_pairs(modis_id TEXT,viirs_id TEXT,distance_km REAL,dt_min REAL,score REAL,label TEXT,assigned INTEGER,PRIMARY KEY(modis_id,viirs_id));
CREATE TABLE IF NOT EXISTS groups(id TEXT PRIMARY KEY,modis_id TEXT,viirs_id TEXT,status TEXT,score REAL);
CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT);
"""


def finite(value):
    if isinstance(value, bool): raise ValueError("boolean numeric value")
    result=float(value)
    if not math.isfinite(result): raise ValueError("nonfinite value")
    return result


def normalize(raw, file_id, number):
    sensor="MODIS" if str(raw['instrument']).upper()=='MODIS' else "VIIRS"
    sat=str(raw['satellite']).upper()
    if sensor=='MODIS' and sat not in {'TERRA','AQUA'}: raise ValueError('unsupported MODIS platform')
    if sensor=='VIIRS' and sat not in {'SNPP','N','S-NPP','SUOMI-NPP','NPP'}: raise ValueError('unsupported VIIRS platform')
    date=str(raw['acq_date']); time=str(raw['acq_time']).zfill(4)
    if len(time)!=4 or not time.isdigit(): raise ValueError('invalid HHMM')
    stamp=datetime.strptime(date+' '+time,'%Y-%m-%d %H%M').replace(tzinfo=timezone.utc)
    if stamp.year not in {2022,2023,2024,2025}: raise ValueError('date outside archive scope')
    lat,lon=finite(raw['latitude']),finite(raw['longitude'])
    if not (-90<=lat<=90 and -180<=lon<=180): raise ValueError('invalid coordinates')
    conf=str(raw['confidence']).lower(); version=str(raw['version'])
    if sensor=='MODIS':
        c=finite(conf)
        if not c.is_integer() or not 0<=c<=100: raise ValueError('invalid MODIS confidence')
        quality=c>=30
    else:
        if conf not in {'l','n','h'}: raise ValueError('invalid VIIRS confidence')
        quality=conf in {'n','h'}
    kind=int(raw['type']) if raw.get('type') is not None else None
    if kind not in {None,0,1,2,3}: raise ValueError('invalid detection type')
    dn=raw['daynight']
    if dn not in {'D','N'}: raise ValueError('invalid day/night')
    def optional(key):
        value=raw.get(key)
        return None if value is None or value=='' else finite(value)
    frp=optional('frp')
    if frp is not None and frp<0: raise ValueError('negative FRP')
    return (f"{file_id}:{number}",file_id,number,sensor,raw['satellite'],stamp.year,stamp.month,date,
            f"{time[:2]}:{time[2:]}",stamp.timestamp(),lat,lon,conf,frp,optional('brightness'),optional('scan'),
            optional('track'),dn,('MODIS ' if sensor=='MODIS' else 'VIIRS S-NPP ')+version,'Unassigned / offshore',kind,
            int(quality and kind==0),'modis-only' if sensor=='MODIS' else 'viirs-only',None,json.dumps(raw,allow_nan=False))


def ingest(connection, path):
    path=Path(path); source=path.read_bytes(); digest=hashlib.sha256(source).hexdigest()
    if connection.execute('SELECT 1 FROM source_files WHERE id=?',(digest,)).fetchone():
        print('Already imported:',path.name,flush=True); return
    rows=json.loads(source.decode('utf-8-sig'))
    if not isinstance(rows,list): raise ValueError('expected JSON array')
    connection.execute('INSERT INTO source_files VALUES (?,?,?,?,?)',(digest,path.name,digest,len(rows),datetime.now(timezone.utc).isoformat()))
    batch=[]; rejected=[]
    for i,row in enumerate(rows,1):
        try: batch.append(normalize(row,digest,i))
        except (ValueError,KeyError,TypeError,OverflowError) as error:
            rejected.append((digest,i,str(error),json.dumps(row)))
        if len(batch)>=5000:
            connection.executemany('INSERT INTO observations VALUES ('+','.join('?'*25)+')',batch);batch=[]
    connection.executemany('INSERT INTO observations VALUES ('+','.join('?'*25)+')',batch)
    connection.executemany('INSERT INTO rejected VALUES (?,?,?,?)',rejected)
    connection.commit(); print('Imported',path.name,len(rows),'rejected',len(rejected),flush=True)


def assign_regions(connection):
    features=json.loads((ROOT/'boundaries/indonesia-adm1.geojson').read_text())['features']
    points=connection.execute('SELECT id,lon,lat FROM observations').fetchall()
    xs=np.array([r[1] for r in points]);ys=np.array([r[2] for r in points])
    updates=[]
    for feature in features:
        polygon=shape(feature['geometry']);w,s,e,n=polygon.bounds
        indices=np.where((xs>=w)&(xs<=e)&(ys>=s)&(ys<=n))[0]
        mask=intersects_xy(polygon,xs[indices],ys[indices])
        updates.extend((feature['properties']['shapeName'],points[i][0]) for i in indices[mask])
    connection.executemany('UPDATE observations SET region=? WHERE id=?',updates)
    connection.commit();print('Assigned administrative boundaries:',len(updates),flush=True)


def match(connection):
    connection.execute('DELETE FROM candidate_pairs');connection.execute('DELETE FROM groups')
    connection.execute("UPDATE observations SET group_id=NULL,status=CASE sensor WHEN 'MODIS' THEN 'modis-only' ELSE 'viirs-only' END")
    m=connection.execute("SELECT id,lon,lat,ts FROM observations WHERE eligible=1 AND sensor='MODIS' ORDER BY id").fetchall()
    v=connection.execute("SELECT id,lon,lat,ts FROM observations WHERE eligible=1 AND sensor='VIIRS' ORDER BY id").fetchall()
    if not m or not v: connection.commit();return
    # Conservative Cartesian screening, followed by exact Haversine/time gates.
    tree=cKDTree([[r[1]*109,r[2]*110,r[3]/1800] for r in v])
    pairs=[]; rr=[];cc=[];cost=[]
    for i,a in enumerate(m):
        for j in sorted(tree.query_ball_point([a[1]*109,a[2]*110,a[3]/1800],1.1,p=np.inf)):
            b=v[j];dt=abs(a[3]-b[3])/60
            phi1,phi2=math.radians(a[2]),math.radians(b[2]);dp=phi2-phi1;dl=math.radians(b[1]-a[1])
            h=math.sin(dp/2)**2+math.cos(phi1)*math.cos(phi2)*math.sin(dl/2)**2
            distance=6371.0088*2*math.asin(min(1,math.sqrt(h)))
            if dt>30 or distance>1: continue
            score=0.6*(1-distance)+0.4*(1-dt/30)
            label='matched' if score>=0.7 else 'possible' if score>=0.45 else 'unmatched'
            pairs.append((a[0],b[0],distance,dt,score,label,0))
            if score>=0.45:rr.append(i);cc.append(j);cost.append(1-score+1e-8)
    # Dummy columns permit every MODIS row to stay unmatched. Positive sparse costs
    # avoid scipy treating genuine zero costs as missing edges.
    rr.extend(range(len(m)));cc.extend(len(v)+i for i in range(len(m)));cost.extend([1.0]*len(m))
    matrix=coo_matrix((cost,(rr,cc)),shape=(len(m),len(v)+len(m))).tocsr()
    ai,bi=min_weight_full_bipartite_matching(matrix)
    assigned={(m[i][0],v[j][0]) for i,j in zip(ai,bi) if j<len(v)}
    output=[];groups=[];updates=[]
    for a,b,d,t,score,label,_ in pairs:
        chosen=(a,b) in assigned;output.append((a,b,d,t,score,label,int(chosen)))
        if chosen:
            gid='G-'+hashlib.sha256((a+b).encode()).hexdigest()[:24]
            groups.append((gid,a,b,label,score));updates.extend([(label,gid,a),(label,gid,b)])
    connection.executemany('INSERT INTO candidate_pairs VALUES (?,?,?,?,?,?,?)',output)
    connection.executemany('INSERT INTO groups VALUES (?,?,?,?,?)',groups)
    connection.executemany('UPDATE observations SET status=?,group_id=? WHERE id=?',updates)
    connection.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',('config',json.dumps(CONFIG)))
    connection.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',('processed_at',datetime.now(timezone.utc).isoformat()))
    connection.commit();print('Candidates',len(pairs),'assigned groups',len(groups),flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('inputs',nargs='+');parser.add_argument('--db',type=Path,default=DB)
    args=parser.parse_args();args.db.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(args.db) as connection:
        connection.executescript(SCHEMA)
        for path in args.inputs:ingest(connection,path)
        assign_regions(connection);match(connection)
        print('Years:',connection.execute('SELECT year,sensor,COUNT(*) FROM observations GROUP BY year,sensor').fetchall(),flush=True)

if __name__=='__main__':main()
