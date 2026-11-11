#!/usr/bin/env python3
"""Optional native RSS proof, never downloader replacement or database writes.

Parent receipt must mark provider_fixture=pinchflat-rss. No implicit activation.
Native failures retain attempts and leave queues paused for explicit cleanup.
"""
import argparse
import base64
import hashlib
import importlib
import json
from pathlib import Path, PurePosixPath
import re
import time
import uuid
import sys
import urllib.parse

s = importlib.import_module('talos-proof-media-safety')
API = importlib.import_module('talos-proof-media-http').API
NS = 'proof-pinchflat'
FEED = 'http://127.0.0.1:7913/feed.xml'
HTML = 'http://127.0.0.1:7913/video/proof-001'
INPUT = 'Proof Browser Fixture (2000).mp4'
INPUT_SHA = '9f754faabc2f1d7a460a8b3ff0ef3f9124c9cab7407af3e66a649c720ae348cb'
QUEUES = ('default','fast_indexing','media_collection_indexing','media_fetching','remote_metadata','local_data')


def expect(ok, message):
    if not ok: raise RuntimeError(message)


def check():
    receipt, _ = s.lease('pinchflat')
    expect(receipt.get('provider_fixture') == 'pinchflat-rss', 'exact provider receipt marker required')
    s.exclusivity('pinchflat')


def save(state, category, value):
    name = 'pinchflat-rss-' + category + '-' + uuid.uuid4().hex + '.json'
    s.write_private(state / name, json.dumps(value))
    return name


def kube(*args, **kwargs):
    check()
    return s.kube('pinchflat', '-n', NS, *args, **kwargs)


def pod():
    pods = json.loads(kube('get','pods','-l','app.kubernetes.io/name=pinchflat','-o','json'))['items']
    active = [p for p in pods if not p['metadata'].get('deletionTimestamp') and p['status']['phase']=='Running']
    expect(len(active)==1, 'expected exactly one running native app pod')
    return active[0]['metadata']['name']


def remote(container, command, *args):
    return kube('exec',pod(),'-c',container,'--','/bin/sh','-ec',command,'proof',*args)


def rpc(state, expression):
    # Native release RPC; expressions in this module are fixed SELECTs or public
    # Oban queue-control calls. No caller-supplied SQL, Ecto inserts or DB edits.
    code = expression + '; IO.puts("PROOF_JSON:" <> Jason.encode!(result))'
    raw = remote('pinchflat','exec /app/bin/pinchflat rpc "$1"',code)
    s.write_private(state / ('pinchflat-rpc-private-' + uuid.uuid4().hex + '.log'), raw)
    lines = [x.removeprefix('PROOF_JSON:') for x in raw.decode().splitlines() if x.startswith('PROOF_JSON:')]
    expect(len(lines)==1, 'native release RPC did not yield one structured result')
    return json.loads(lines[0])


SQL = {
 'profiles':'SELECT id,name,output_path_template,download_subs,download_auto_subs,embed_subs,download_thumbnail,embed_thumbnail,download_source_images,download_metadata,embed_metadata,download_nfo,sponsorblock_behaviour,shorts_behaviour,livestream_behaviour,preferred_resolution,media_container FROM media_profiles ORDER BY id',
 'sources':'SELECT id,media_profile_id,collection_id,collection_name,collection_type,original_url,custom_name,enabled,download_media,last_indexed_at FROM sources ORDER BY id',
 'items':'SELECT id,source_id,media_id,title,original_url,uploaded_at,duration_seconds,media_downloaded_at,media_filepath,media_size_bytes,last_error FROM media_items ORDER BY id',
 'jobs':'SELECT coalesce(t.source_id,m.source_id) AS source_id,t.media_item_id,j.id,j.state,j.queue,j.worker,j.attempt,j.completed_at FROM tasks t JOIN oban_jobs j ON j.id=t.job_id LEFT JOIN media_items m ON m.id=t.media_item_id ORDER BY j.id',
 'updater':"SELECT id,state,worker,attempt,attempted_at,completed_at FROM oban_jobs WHERE worker='Pinchflat.YtDlp.UpdateWorker' ORDER BY id",
 'executing':"SELECT id,queue,worker FROM oban_jobs WHERE state='executing' ORDER BY id",
}


def native(state):
    queries = ','.join('{' + json.dumps(k) + ',' + json.dumps(v) + '}' for k,v in SQL.items())
    code = ('result = Map.new(['+queries+'], fn {name,sql} -> '
            'r = Ecto.Adapters.SQL.query!(Pinchflat.Repo,sql,[]); '
            '{name,Enum.map(r.rows,fn row -> Map.new(Enum.zip(r.columns,row)) end)} end)')
    value = rpc(state, code)
    expect(set(value)==set(SQL), 'native observation shape differs from reviewed schema')
    return value


def queues(state, resume=None):
    expect(resume is None or resume in ('media_collection_indexing','media_fetching'), 'unapproved queue activation')
    atoms = ','.join(':'+q for q in QUEUES)
    rpc(state, 'Enum.each(['+atoms+'],fn q -> :ok = Oban.pause_queue(queue: q) end); result = %{paused: true}')
    for _ in range(20):
        if not native(state)['executing']: break
        time.sleep(1)
    else: raise RuntimeError('native executing jobs did not drain; no concurrent extractor stage allowed')
    if resume:
        configured = rpc(state, 'result = Map.new(Application.fetch_env!(:pinchflat,Oban)[:queues])')
        expect(configured.get(resume)==1, 'selected native queue concurrency must be one; it is not a global limit')
        rpc(state, ':ok = Oban.resume_queue(queue: :'+resume+'); result = %{resumed: '+json.dumps(resume)+'}')


def stock(state):
    configured = rpc(state, 'result = Application.fetch_env!(:pinchflat,:yt_dlp_executable)')
    expect(configured=='/usr/local/bin/yt-dlp', 'native downloader path differs from reviewed bundled binary')
    lines = remote('pinchflat','test "$(command -v yt-dlp)" = /usr/local/bin/yt-dlp; sha256sum /usr/local/bin/yt-dlp; /usr/local/bin/yt-dlp --version').decode().splitlines()
    expect(len(lines)==2 and re.fullmatch('[a-f0-9]{64}',lines[0].split()[0]) and re.fullmatch(r'[A-Za-z0-9.+_-]{1,100}',lines[1]), 'bundled binary identity unreadable')
    result = {'path':configured,'sha256':lines[0].split()[0],'version':lines[1]}
    save(state,'stock-downloader',result)
    return result


def stats():
    return json.loads(remote('rss-fixture','test -f /proof-stats/latest.json; head -c 65536 /proof-stats/latest.json'))


def coverage(before, after):
    expect(before['instance_id']==after['instance_id'] and before['media_sha256']==after['media_sha256']==INPUT_SHA,
           'fixture restarted or input identity changed')
    first,last = before['phases']['download'],after['phases']['download']
    expect(first['media_body_bytes']==first['media_unique_bytes']==0, 'download phase must begin at actual zero baseline')
    expect(last['media_unique_bytes']==after['media_size']==120214 and last['media_body_bytes']>=120214,
           'no complete unique byte coverage during native download phase')
    expect(last['routes']['/media/proof-001.mp4']>0, 'no native media request')


def file_hash(path, destination):
    value = PurePosixPath(path)
    expect(value.is_absolute() and str(value).startswith(destination+'/') and '..' not in value.parts and value.suffix=='.mp4', 'native output escaped unique destination')
    lines = remote('pinchflat','test -f "$1"; test ! -L "$1"; wc -c < "$1"; sha256sum "$1"',path).decode().splitlines()
    expect(len(lines)==2 and int(lines[0])==120214 and lines[1].split()[0]==INPUT_SHA, 'native file size/hash differs; remux is NOT an exact-byte pass')


def completion(observed, source_id):
    items = [i for i in observed['items'] if i['source_id']==source_id]
    expect(len(items)==1, 'expected one real indexed media item')
    item = items[0]
    expect(item['original_url']==HTML and item['media_id'] and item['title'] and item['uploaded_at'] and item['duration_seconds']==12,
           'independently extracted required metadata differs or is missing')
    jobs = [j for j in observed['jobs'] if j['source_id']==source_id and j['media_item_id']==item['id'] and j['worker']=='Pinchflat.Downloading.MediaDownloadWorker' and j['state']=='completed' and j['completed_at']]
    indexed = [j for j in observed['jobs'] if j['source_id']==source_id and j['worker']=='Pinchflat.SlowIndexing.MediaCollectionIndexingWorker' and j['state']=='completed' and j['completed_at']]
    expect(indexed, 'no actual completed native slow-index job linked to Source')
    expect(item['media_downloaded_at'] and not item['last_error'] and item['media_filepath'] and item['media_size_bytes']==120214 and jobs,
           'native item/download job is not genuinely completed')
    return item, sorted(jobs+indexed, key=lambda job:job['id'])


def prepare(state, fixture):
    s.pinchflat_provider_guard();s.require_helpers_deleted('pinchflat')
    expect(fixture.name==INPUT and hashlib.sha256(s.read_private(fixture,binary=True)).hexdigest()==INPUT_SHA,
           'exact retained immutable browser fixture required; never regenerate or replace it here')
    deployment = json.loads(kube('get','deployment','pinchflat','-o','json'))
    expect(deployment['spec'].get('replicas',1)==0 and not json.loads(kube('get','pods','-o','json'))['items'], 'prepare requires stopped controller and all app/helper pods deleted')
    import yaml
    patch = yaml.safe_load((s.ROOT/'kubernetes/apps/media/pinchflat-rss/provider.yaml').read_text())
    source = (s.ROOT/'scripts/talos-proof-media-pinchflat-fixture.py').read_text()
    code_name,input_name = 'rss-code-'+hashlib.sha256(source.encode()).hexdigest()[:16],'rss-input-'+INPUT_SHA[:16]
    labels = {'app.kubernetes.io/part-of':'talos-proof','app.kubernetes.io/name':'pinchflat'}
    for resource in [
        {'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':code_name,'namespace':NS,'labels':labels},'immutable':True,'data':{'origin.py':source}},
        {'apiVersion':'v1','kind':'Secret','metadata':{'name':input_name,'namespace':NS,'labels':labels},'type':'Opaque','immutable':True,'data':{'fixture.mp4':base64.b64encode(s.read_private(fixture,binary=True)).decode()}}]:
        kube('apply','-f','-',data=json.dumps(resource).encode())
    volumes = patch['spec']['template']['spec']['volumes']
    next(v for v in volumes if v['name']=='rss-code')['configMap']['name']=code_name
    next(v for v in volumes if v['name']=='rss-input')['secret']['secretName']=input_name
    before = {v['name']:v['persistentVolumeClaim'] for v in deployment['spec']['template']['spec']['volumes'] if 'persistentVolumeClaim' in v}
    kube('patch','deployment','pinchflat','--type=strategic','-p',json.dumps(patch))
    actual = json.loads(kube('get','deployment','pinchflat','-o','json'))
    after = {v['name']:v['persistentVolumeClaim'] for v in actual['spec']['template']['spec']['volumes'] if 'persistentVolumeClaim' in v}
    expect(before==after and actual['spec']['replicas']==0, 'profile preparation changed retained PVC references or activation state')
    return {'input_sha256':INPUT_SHA,'code_configmap':code_name,'input_secret':input_name,'claims':after,'result':'PREPARED_STOPPED_ONLY'}


def stage_executing(observed, queue):
    expect(len(observed['executing']) <= 1 and all(j['queue']==queue for j in observed['executing']),
           'unexpected concurrent native job during isolated extractor stage')


def exercise(state, ca):
    s.pinchflat_provider_guard();s.require_helpers_deleted('pinchflat')
    queues(state)
    before = native(state)
    expect(not before['sources'] and not before['items'], 'RSS exercise requires no existing Sources/items; retain existing profiles')
    binary = stock(state)
    raw = remote('pinchflat','exec env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY /usr/local/bin/yt-dlp --ignore-config --no-cache-dir --socket-timeout 3 --skip-download --no-playlist --dump-single-json "$1"',HTML)
    s.write_private(state/('pinchflat-html-extraction-private-'+uuid.uuid4().hex+'.json'),raw)
    metadata = json.loads(raw)
    expect(metadata.get('id') and metadata.get('title') and metadata.get('upload_date')=='20260101' and metadata.get('duration')==12,
           'actual bundled generic HTML extractor did not yield required independent metadata')
    destination = '/downloads/rss-proof-'+uuid.uuid4().hex
    identity = rpc(state, 'result = %{uid: String.trim(elem(System.cmd("id",["-u"]),0)), gid: String.trim(elem(System.cmd("id",["-g"]),0))}')
    expect(all(re.fullmatch('[0-9]{1,10}',identity[k]) for k in ('uid','gid')), 'native runtime ownership unreadable')
    remote('pinchflat','test ! -e "$1"; mkdir "$1"; chown "$2:$3" "$1"; chmod 750 "$1"; test -z "$(ls -A "$1")"',destination,identity['uid'],identity['gid'])
    credential = json.loads(s.read_private(state/'credentials.json'))['pinchflat']
    api = API('https://pinchflat.proof.invalid:18443',service='pinchflat',ca=s.private_file(ca))
    api.headers['Authorization']='Basic '+base64.b64encode((credential['username']+':'+credential['password']).encode()).decode()
    # Only native CSRF-protected HTTP creates app records. RPC remains SELECT-only.
    sys.path.insert(0,str(s.ROOT/'tests'))
    service = importlib.import_module('talos-proof-media-services')
    profile_name='proof-rss-'+uuid.uuid4().hex
    api.call('/media_profiles','POST',form={'_csrf_token':service.csrf(api.call('/media_profiles/new',raw=True)),
        'media_profile[name]':profile_name,'media_profile[output_path_template]':destination.removeprefix('/downloads/')+'/{{ id }}.{{ ext }}',
        'media_profile[download_metadata]':'false','media_profile[embed_metadata]':'false','media_profile[download_nfo]':'false',
        'media_profile[download_thumbnail]':'false','media_profile[download_source_images]':'false','media_profile[sponsorblock_behaviour]':'disabled'})
    profiles = native(state)['profiles']
    selected = [p for p in profiles if p['name']==profile_name]
    expect(len(selected)==1, 'native media profile creation failed')
    profile_id = selected[0]['id']
    attempt = {'destination':destination,'binary_before':binary,'profile_id':profile_id,'profiles_before':before['profiles']}
    save(state,'attempt',attempt)
    check()
    api.call('/sources','POST',form={'_csrf_token':service.csrf(api.call('/sources/new',raw=True)),
        'source[original_url]':FEED,'source[custom_name]':profile_name,'source[media_profile_id]':profile_id,
        'source[fast_index]':'false','source[download_media]':'true','source[cookie_behaviour]':'disabled','source[index_frequency_minutes]':'1440'})
    sources = native(state)['sources']
    expect(len(sources)==1 and sources[0]['original_url']==FEED and sources[0]['collection_type']=='playlist'
           and sources[0]['collection_id'] and sources[0]['collection_name'], 'native Source validation/classification failed')
    source = sources[0]
    save(state,'native-source',source)
    queues(state,'media_collection_indexing')
    observed = None
    for _ in range(45):
        observed=native(state)
        stage_executing(observed,'media_collection_indexing')
        if observed['items'] and not observed['executing']:break
        time.sleep(2)
    queues(state)
    expect(observed and len(observed['items'])==1 and not observed['items'][0]['media_downloaded_at'], 'slow indexing failed or native download ran before isolated phase')
    remote('rss-fixture','printf download > /proof-stats/phase')
    baseline = None
    for _ in range(10):
        baseline=stats()
        if baseline['phase']=='download':break
        time.sleep(.2)
    expect(baseline['phase']=='download' and baseline['phases']['download']['media_body_bytes']==0, 'no true fresh native-download phase baseline')
    save(state,'download-baseline',baseline)
    queues(state,'media_fetching')
    success = None
    for _ in range(60):
        observed=native(state)
        stage_executing(observed,'media_fetching')
        try:success=completion(observed,source['id'])
        except RuntimeError:pass
        if success and not observed['executing']:break
        time.sleep(2)
    queues(state)
    item,jobs=completion(native(state),source['id'])
    expect(item['media_id']==metadata['id'] and item['title']==metadata['title']
           and str(item['uploaded_at']).startswith('2026-01-01'), 'native indexed/downloaded identity differs from independent HTML extraction')
    final=stats();coverage(baseline,final);file_hash(item['media_filepath'],destination)
    binary_after=stock(state);expect(binary_after==binary,'stock downloader changed during actual pipeline')
    expect(all(p in native(state)['profiles'] for p in before['profiles']), 'earlier media profiles changed')
    # Capture the final durable Source after native indexing updated last_indexed_at.
    source=next(x for x in native(state)['sources'] if x['id']==source['id'])
    return dict(attempt,independent_html={k:metadata[k] for k in ('id','title','upload_date','duration')},updater_before=before['updater'],updater_after=native(state)['updater'],source=source,item=item,jobs=jobs,fixture_before=baseline,fixture_after=final,binary_after=binary_after)


def verify(state, record):
    check()
    expect(Path(record).name==record, 'record must be exact immutable private-state basename')
    marker=json.loads(s.read_private(state/record));observed=native(state)
    expect(not observed['executing'], 'verify requires native queues idle before state comparison')
    source=next((x for x in observed['sources'] if x['id']==marker['source']['id']),None)
    item,jobs=completion(observed,marker['source']['id'])
    expect(source==marker['source'] and item==marker['item'] and jobs==marker['jobs'], 'native source/item/completed jobs changed across replacement/recovery')
    expect(all(p in observed['profiles'] for p in marker['profiles_before']), 'earlier profiles lost across recovery')
    file_hash(item['media_filepath'],marker['destination'])
    expect(stock(state)==marker['binary_after'], 'replacement changed actual bundled downloader identity')
    return {'result':'PASS','scope':'existing native Source/item/job/output verified before submission or destination writes'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['prepare','exercise','verify'])
    p.add_argument('--state',required=True,type=Path)
    p.add_argument('--fixture',type=Path)
    p.add_argument('--ca',type=Path)
    p.add_argument('--record')
    a=p.parse_args();state=s.private_dir(a.state)
    if a.action=='prepare':
        expect(a.fixture is not None,'prepare needs exact immutable fixture');result=prepare(state,a.fixture)
    elif a.action=='exercise':
        expect(a.ca is not None,'exercise requires trusted Gateway CA');result=exercise(state,a.ca)
    else:
        expect(a.record is not None,'verify needs prior passed record');result=verify(state,a.record)
    name=save(state,a.action+'-result',result)
    print(json.dumps({'action':a.action,'result':result.get('result','PASS'),'record':name}))


if __name__=='__main__':
    try:main()
    except Exception as exc:
        try:
            supplied = Path(sys.argv[sys.argv.index('--state')+1])
            state = s.private_dir(supplied)
            save(state,'failure',{'error_type':type(exc).__name__,'http_status':getattr(exc,'code',None)})
        except Exception:
            pass
        # Fixed errors only; never echo credentials, native logs or auth URLs.
        print(json.dumps({'result':'FAIL','error_type':type(exc).__name__,'http_status':getattr(exc,'code',None),
                          'check':str(exc) if isinstance(exc,RuntimeError) else None}))
        raise SystemExit(1)
