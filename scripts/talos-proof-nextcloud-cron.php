<?php
/** Version-bound native payload for the exact-receipt serial supervisor.
 * Public source parity is checked at runtime; this is not image attestation.
 * No manual application or direct payload invocation is authorized.
 */
declare(strict_types=1);
umask(0077);
const CLEANUP_CLASS = 'OC\\Authentication\\Token\\TokenCleanupJob';
// Only the receipt-bound serial supervisor may supply this payload.

final class GateFailure extends RuntimeException {
    public function __construct(string $gate, public readonly array $context = []) { parent::__construct($gate); }
}
function need(bool $condition, string $gate, array $context = []): void {
    if (!$condition) { throw new GateFailure($gate, $context); }
}
function privateError(Throwable $error): array {
    // No environment dump, trace/args or opaque token values. This record is
    // private captured output only; the supervisor's public error stays fixed.
    $message = $error->getMessage();
    foreach (['POSTGRES_PASSWORD','NEXTCLOUD_ADMIN_PASSWORD','REDIS_HOST_PASSWORD'] as $name) {
        $secret = getenv($name);
        if (is_string($secret) && $secret !== '') { $message = str_replace($secret, '[redacted]', $message); }
    }
    $message = preg_replace('/[A-Za-z0-9+\/_=\-]{24,}/', '[opaque-redacted]', $message);
    $message = preg_replace('/[^\x20-\x7e]/', '?', $message);
    return ['message'=>substr($message,0,1024),
        'source_file'=>substr(basename($error->getFile()),0,128), 'source_line'=>$error->getLine(),
        'context'=>$error instanceof GateFailure ? $error->context : []];
}
function hashCheck(string $root, string $relative, string $expected, string $gate): void {
    need(!str_contains($relative, '..') && $relative !== '' && $relative[0] !== '/', 'invalid source index');
    need((bool)preg_match('/^[0-9a-f]{64}$/D',$expected), 'invalid expected source hash');
    $path = $root . '/' . $relative;
    $actual = is_file($path) && !is_link($path) ? @hash_file('sha256',$path) : false;
    need(is_string($actual) && hash_equals($expected,$actual), $gate,
        ['source_root'=>$root,'source_relative'=>substr($relative,0,256),
         'expected_sha256'=>$expected,'actual_sha256'=>$actual === false ? 'unavailable' : $actual]);
}
function exclusive(string $path, array $value): void {
    $stream = fopen($path, 'x');
    need($stream !== false, 'exclusive private journal creation failed');
    try {
        need(chmod($path, 0600), 'journal permissions failed');
        $data = json_encode($value, JSON_THROW_ON_ERROR);
        need(fwrite($stream, $data) === strlen($data) && fflush($stream), 'journal write failed');
        need(function_exists('fsync') && fsync($stream), 'durable journal fsync unavailable');
    } finally { fclose($stream); }
}
function cgroups(): array {
    $result = [];
    foreach (['memory.current', 'memory.peak', 'memory.events', 'memory.stat'] as $file) {
        $value = @file_get_contents('/sys/fs/cgroup/' . $file);
        $result[$file] = $value === false ? ['gap' => 'unavailable'] : trim($value);
    }
    return $result;
}
function parity(string $root): void {
    // Exact approved public artifact bridge; original Git index is untouched.
    hashCheck('/proof','packaged-metadata.json','86a6fd499c4bc438efc6cc0e4b87b11b69c8c21b111de29c6f2fce3d73bde32c','reviewed packaged metadata drift');
    $bridge=json_decode(file_get_contents('/proof/packaged-metadata.json'),true,512,JSON_THROW_ON_ERROR);
    need(PHP_OS_FAMILY === 'Linux' && php_uname('m') === 'x86_64', 'reviewed packaged metadata platform mismatch');
    $hashes = json_decode(file_get_contents('/proof/core-hashes.json'), true, 512, JSON_THROW_ON_ERROR);
    need(count($hashes) >= 20, 'incomplete reviewed core source index');
    need(($hashes['version.php'] ?? null) === $bridge['overrides']['version.php']['packaged_sha256'], 'packaged version metadata hash binding mismatch');
    foreach ($hashes as $relative => $hash) {
        need(!str_contains($relative, '..') && $relative[0] !== '/', 'invalid source index');
        $path = $root . '/' . $relative;
        for ($part = $path; $part !== $root; $part = dirname($part)) {
            need(!is_link($part), 'symlink in reviewed source path',
                ['source_root'=>$root,'source_relative'=>substr($relative,0,256),
                 'expected_sha256'=>$hash,'actual_sha256'=>'unavailable']);
        }
        hashCheck($root,$relative,$hash,'actual core source parity mismatch');
    }
}
function rows(string $table, array $columns): array {
    $db = \OCP\Server::get(\OCP\IDBConnection::class);
    $qb = $db->getQueryBuilder();
    return $qb->select(...$columns)->from($table)->executeQuery()->fetchAllAssociative();
}
function tokenRows(): array {
    // Physical DB reads only: no cached token getter used as deletion evidence.
    return rows('authtoken', ['id', 'uid', 'name', 'type', 'remember', 'last_activity']);
}
function cleanupRow(): array {
    $found = array_values(array_filter(rows('jobs', ['id','class','last_run','last_checked','reserved_at']),
        fn($r) => $r['class'] === CLEANUP_CLASS));
    need(count($found) === 1, 'cleanup job missing or ambiguous');
    return $found[0];
}
function due(array $job): void {
    need((int)$job['last_run'] >= 0 && time() - (int)$job['last_run'] > 86400
        && (int)$job['reserved_at'] === 0 && (int)$job['last_checked'] <= time(),
        'native daily cleanup not due/unreserved; class filter does not bypass interval');
}
function snapshot($config): array {
    return ['session_lifetime' => [
        'present' => in_array('session_lifetime', $config->getSystemKeys(), true),
        'value' => $config->getSystemValue('session_lifetime')],
        'backgroundjobs_mode' => [
        'present' => in_array('backgroundjobs_mode', $config->getAppKeys('core'), true),
        'value' => $config->getAppValue('core', 'backgroundjobs_mode')]];
}
function nativeContext(): array {
    parity('/usr/src/nextcloud');
    parity('/var/www/html');
    $hashes=json_decode(file_get_contents('/proof/docker-hashes.json'),true,512,JSON_THROW_ON_ERROR);
    foreach ($hashes as $path=>$hash) {
        hashCheck('/var/www/html',$path,$hash,'retained Docker config mismatch');
    }
    $allowed=array_map('basename',array_keys($hashes));
    $allowed=array_merge($allowed,['config.php','config.sample.php','.htaccess']);
    foreach (array_diff(scandir('/var/www/html/config'),['.','..']) as $name) {
        need(in_array($name,$allowed,true) && !is_link('/var/www/html/config/'.$name), 'unknown retained config fragment');
    }
    need(is_file('/var/www/html/config/config.php') && !is_link('/var/www/html/config/config.php')
        && fileowner('/var/www/html/config/config.php') === 33, 'retained config ownership invalid');
    require_once '/var/www/html/lib/base.php';
    $config = \OCP\Server::get(\OCP\IConfig::class);
    need($config->getSystemValue('installed') === true && $config->getSystemValue('maintenance', false) === false
        && $config->getSystemValue('version') === '35.0.2.2'
        && $config->getSystemValue('dbtype') === 'pgsql'
        && $config->getSystemValue('dbhost') === 'postgres'
        && $config->getSystemValue('dbname') === 'nextcloud'
        && $config->getSystemValue('dbuser') === 'nextcloud'
        && $config->getSystemValue('datadirectory') === '/var/www/html/data', 'retained native configuration mismatch');
    need(!\OC::checkUpgrade(), 'pending native upgrade blocks');
    need(\OCP\Server::get(\OCP\IUserManager::class)->get('proof') !== null, 'original proof user absent; never recreate/reset');
    $redis = $config->getSystemValue('redis');
    need(is_array($redis) && in_array(($redis['host'] ?? null), ['redis', 'tcp://redis'], true)
        && ($redis['password'] ?? null) === getenv('REDIS_HOST_PASSWORD')
        && is_string($redis['password']) && $redis['password'] !== '', 'authenticated Redis configuration unverified');
    need($config->getSystemValue('memcache.locking') === '\\OC\\Memcache\\Redis', 'native Redis locking not configured');
    // Read-only connection assertion; never FLUSH/SET/CONFIG.
    $client = new Redis();
    need($client->connect('redis', (int)($redis['port'] ?? 6379), 3.0)
        && $client->auth($redis['password']) && $client->ping() !== false, 'native Redis authentication failed');
    $client->close();
    return [$config, \OCP\Server::get(\OC\Authentication\Token\IProvider::class)];
}
function eligible(array $row, $config, int $until): bool {
    $type = (int)$row['type'];
    $key = match ($type) {
        \OCP\Authentication\Token\IToken::TEMPORARY_TOKEN => (int)$row['remember'] === 0 ? 'session_lifetime' : 'remember_login_cookie_lifetime',
        \OCP\Authentication\Token\IToken::WIPE_TOKEN => 'token_auth_wipe_token_retention',
        \OCP\Authentication\Token\IToken::PERMANENT_TOKEN => 'token_auth_token_retention',
        default => throw new RuntimeException('unknown retained token class'),
    };
    $defaults = ['session_lifetime'=>86400, 'remember_login_cookie_lifetime'=>1296000,
        'token_auth_wipe_token_retention'=>5184000, 'token_auth_token_retention'=>31536000];
    $ttl = $config->getSystemValueInt($key, $defaults[$key]);
    need($ttl > 3600, 'retention must exceed bounded run horizon');
    return (int)$row['last_activity'] < $until - $ttl;
}
function fixture(string $journal): array {
    [$config, $provider] = nativeContext();
    $intent = json_decode(file_get_contents('/proof/intent.json'), true, 512, JSON_THROW_ON_ERROR);
    $beforeJob = cleanupRow(); due($beforeJob);
    foreach (tokenRows() as $row) {
        need(!eligible($row, $config, time()+900), 'out-of-scope token eligible during run');
        foreach ($intent['tokens'] as $t) { need($row['name'] !== $t['name'], 'fixture name already exists'); }
    }
    need(!file_exists($journal) && mkdir($journal, 0700), 'new private run journal required');
    $state = ['settings'=>snapshot($config), 'job'=>$beforeJob, 'created_at'=>time(), 'tokens'=>$intent['tokens']];
    exclusive($journal . '/before.json', $state); // intent already exported off-pod before this Job
    $mapper = \OCP\Server::get(\OC\Authentication\Token\PublicKeyTokenMapper::class);
    foreach ($state['tokens'] as $kind=>$token) {
        $entity = $provider->generateToken(bin2hex(random_bytes(32)), 'proof', 'proof', null, $token['name'],
            \OCP\Authentication\Token\IToken::TEMPORARY_TOKEN, $token['remember']);
        need($entity instanceof \OC\Authentication\Token\PublicKeyToken && $entity->getUID() === 'proof'
            && $entity->getName() === $token['name'] && $entity->getPassword() === null, 'native owned entity invalid');
        exclusive($journal . '/' . $kind . '.json', ['id'=>$entity->getId(), 'name'=>$token['name']]);
        if ($kind === 'candidate') {
            // Entity dirty tracking + native mapper updates ONLY this newly inserted owned entity.
            // Synthetic age, NOT evidence of real elapsed expiry. Global TTL is unchanged.
            $entity->setLastActivity(time() - $config->getSystemValueInt('session_lifetime',86400) - 60);
            $mapper->update($entity);
        }
    }
    return ['synthetic_age'=>true, 'owned'=>array_values(array_filter(tokenRows(),
        fn($r)=>in_array($r['name'], array_column($state['tokens'],'name'), true)))];
}
function beforeObservation(string $journal): array {
    [$config] = nativeContext();
    $state = json_decode(file_get_contents($journal . '/before.json'), true, 512, JSON_THROW_ON_ERROR);
    $physical = tokenRows(); $own = [];
    foreach ($physical as $row) {
        $kind = array_search($row['name'], array_column($state['tokens'], 'name'), true);
        if ($kind === false) { need(!eligible($row,$config,time()+600), 'out-of-scope token now eligible'); continue; }
        $own[] = $row;
    }
    need(count($own) === 2, 'two owned fixtures required');
    foreach ($state['tokens'] as $kind=>$token) {
        $found = array_values(array_filter($own,fn($r)=>$r['name']===$token['name']));
        $id = json_decode(file_get_contents($journal.'/'.$kind.'.json'),true,512,JSON_THROW_ON_ERROR)['id'];
        need(count($found)===1 && (int)$found[0]['id']===$id && $found[0]['uid']==='proof'
            && (int)$found[0]['type']===0 && (int)$found[0]['remember']===$token['remember'], 'owned fixture identity invalid');
        need(eligible($found[0],$config,time()) === ($kind==='candidate'), 'candidate/control age invalid');
    }
    due(cleanupRow());
    exclusive($journal.'/fixture.json',['rows'=>$own,'observed_at'=>time()]);
    return ['synthetic_age'=>true,'owned'=>$own,'job'=>cleanupRow()];
}
function restore(string $journal): void {
    [$config, $provider] = nativeContext();
    $state = json_decode(file_get_contents($journal . '/before.json'), true, 512, JSON_THROW_ON_ERROR);
    // Failure cleanup is distinct from acceptance. Only exact new fixture names
    // with expected user/type/remember are eligible for native invalidation.
    foreach (tokenRows() as $row) {
        foreach ($state['tokens'] as $token) {
            if ($row['name'] !== $token['name']) { continue; }
            need($row['uid'] === 'proof' && (int)$row['type'] === \OCP\Authentication\Token\IToken::TEMPORARY_TOKEN
                && (int)$row['remember'] === $token['remember'], 'synthetic token ownership mismatch');
            $provider->invalidateTokenById('proof', (int)$row['id']);
        }
    }
    $ownedNames=array_column($state['tokens'],'name');
    need(count(array_filter(tokenRows(),fn($r)=>in_array($r['name'],$ownedNames,true)))===0, 'owned fixture cleanup incomplete');
    $old = $state['settings'];
    need(snapshot($config)['session_lifetime'] === $old['session_lifetime'], 'global TTL changed unexpectedly');
    if ($old['backgroundjobs_mode']['present']) { $config->setAppValue('core', 'backgroundjobs_mode', $old['backgroundjobs_mode']['value']); }
    else { $config->deleteAppValue('core', 'backgroundjobs_mode'); }
    need(snapshot($config) === $old, 'exact typed setting restoration failed');
    exclusive($journal . '/restored.json', ['restored_at' => time()]);
}
function assertion(string $journal): array {
    [, $provider] = nativeContext();
    $before = json_decode(file_get_contents($journal . '/fixture.json'), true, 512, JSON_THROW_ON_ERROR);
    $state = json_decode(file_get_contents($journal . '/before.json'), true, 512, JSON_THROW_ON_ERROR);
    $physical = tokenRows();
    $candidate = array_values(array_filter($before['rows'], fn($r) => $r['name'] === $state['tokens']['candidate']['name']));
    $control = array_values(array_filter($before['rows'], fn($r) => $r['name'] === $state['tokens']['control']['name']));
    need(count($candidate) === 1 && count($control) === 1, 'before-state invalid');
    need(count(array_filter($physical, fn($r) => (int)$r['id'] === (int)$candidate[0]['id'])) === 0, 'expired candidate physically survives');
    need(count(array_filter($physical, fn($r) => $r === $control[0])) === 1, 'live control does not survive unchanged');
    $job = cleanupRow();
    need((int)$job['id'] === (int)$state['job']['id'] && (int)$job['last_run'] > (int)$state['job']['last_run']
        && (int)$job['last_run'] >= $before['observed_at'] && (int)$job['last_run'] <= time()
        && (int)$job['reserved_at'] === 0, 'native scheduling metadata did not advance');
    $lastcron = \OCP\Server::get(\OCP\IConfig::class)->getAppValue('core', 'lastcron');
    need(ctype_digit($lastcron) && (int)$lastcron >= $before['observed_at'] && (int)$lastcron <= time(), 'lastcron corroboration missing');
    exclusive($journal . '/acceptance.json', ['candidate_physically_absent' => true,
        'control_physically_survives' => true, 'observed_at' => time()]);
    restore($journal); // native harness cleanup is AFTER acceptance observation
    return ['native_side_effect' => true, 'restored' => true];
}
function inventory(string $root): array {
    need(is_dir($root) && !is_link($root), 'volume root absent/symlink');
    $allowed=array_merge(array_diff(scandir('/usr/src/nextcloud'),['.','..']),['data']);
    foreach (array_diff(scandir($root),['.','..']) as $name) {
        need(in_array($name,$allowed,true) || preg_match('/^\.proof-(cron|install)-[0-9a-f-]{36}$/D',$name)===1, 'unknown retained volume entry');
    }
    $count = 0;
    $walk = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($root, FilesystemIterator::SKIP_DOTS));
    foreach ($walk as $file) {
        need(!$file->isLink() && ($file->isFile() || $file->isDir()) && $file->getOwner() === 33,
            'unknown retained ownership/type/symlink');
        need(++$count < 500000, 'bounded retained inventory exceeded');
    }
    return ['entries'=>$count, 'empty'=>count(array_diff(scandir($root),['.','..']))===0];
}
function preflight(bool $emptyOnly = false): array {
    parity('/usr/src/nextcloud');
    $docker = json_decode(file_get_contents('/proof/docker-hashes.json'),true,512,JSON_THROW_ON_ERROR);
    foreach ($docker as $path=>$hash) {
        hashCheck('/usr/src/nextcloud',$path,$hash,'packaged Docker config parity mismatch');
    }
    $volume = inventory('/var/www/html');
    if ($emptyOnly) { need($volume['empty'], 'diagnostic requires empty HTML; no retained core bootstrap'); }
    $db = new PDO('pgsql:host=postgres;dbname=nextcloud;connect_timeout=3','nextcloud',getenv('POSTGRES_PASSWORD'),
        [PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);
    $db->exec('SET default_transaction_read_only = on');
    $tables = $db->query("SELECT (SELECT count(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%') + (SELECT count(*) FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema')) + (SELECT count(*) FROM pg_catalog.pg_namespace WHERE nspname NOT IN ('public','pg_catalog','information_schema') AND nspname NOT LIKE 'pg_toast%' AND nspname NOT LIKE 'pg_temp%')")->fetchColumn();
    $r = new Redis();
    need($r->connect('redis',6379,3.0) && $r->auth(getenv('REDIS_HOST_PASSWORD')) && $r->ping()!==false,
        'read-only authenticated Redis preflight failed'); $r->close();
    if ($volume['empty']) { need((int)$tables===0, 'nonempty DB with empty volume blocks install'); }
    else { nativeContext(); need((int)$tables>0, 'retained volume with empty DB blocks'); }
    return ['empty'=>$volume['empty'],'inventory'=>$volume,'db_tables'=>(int)$tables,'redis_authenticated'=>true];
}
function nativeCommand(array $args, string $log): void {
    $f = fopen($log,'x'); need($f!==false && chmod($log,0600), 'private native log creation failed');
    try {
        $p = @proc_open($args,[0=>['file','/dev/null','r'],1=>$f,2=>$f],$pipes,'/var/www/html');
        $started = is_resource($p); $exit = $started ? proc_close($p) : null;
        $context = ['private_child_log'=>substr($log,0,256),'exit_code'=>$exit];
        // Durably retain even a failing child's log BEFORE throwing, no argv.
        need(fflush($f) && fsync($f), 'native log fsync failed', $context);
        need($started && $exit===0, 'native process failed; preserve partial state', $context);
    } finally { fclose($f); }
}
function installOrVerify(string $run): array {
    $pre = preflight();
    if ($pre['empty']) {
        // Exactly once: rsync without --delete, no entrypoint, retries, chown or repair.
        nativeCommand(['rsync','-rlD','/usr/src/nextcloud/','/var/www/html/'],'/tmp/install-copy-'.$run);
        nativeCommand(['php','/var/www/html/occ','maintenance:install','--no-interaction','--database=pgsql',
            '--database-host=postgres','--database-name=nextcloud','--database-user=nextcloud',
            '--database-pass='.getenv('POSTGRES_PASSWORD'),'--admin-user=proof',
            '--admin-pass='.getenv('NEXTCLOUD_ADMIN_PASSWORD'),'--data-dir=/var/www/html/data'],
            '/var/www/html/.proof-install-'.$run);
    }
    nativeContext();
    return ['native_install_or_retained_verify'=>true,'fresh_install'=>$pre['empty']];
}
try {
    $phase = $argv[1] ?? ''; $run = $argv[2] ?? '';
    need((bool)preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/D',$run),'UUID required');
    $journal = '/var/www/html/.proof-cron-'.$run;
    switch ($phase) {
        case 'preflight': $result=preflight(); break;
        case 'diagnose-preflight':
            need(getenv('PROOF_PHASE') === 'diagnose-preflight', 'diagnostic scope only');
            $result=preflight(true); break;
        case 'install-or-verify': $result=installOrVerify($run); break;
        case 'fixture': $result=fixture($journal); break;
        case 'before': $result=beforeObservation($journal); break;
        case 'cron-precheck':
            // Internal child only; never a public phase, Job or grant scope.
            need(getenv('PROOF_PHASE') === 'cron', 'internal cron precheck only');
            nativeContext(); due(cleanupRow());
            $result=['native_daily_due_precheck'=>true]; break;
        case 'cron':
            // Keep this parent free of Nextcloud core. Wait for one heavy child
            // to exit before starting the next, all within the same cgroup.
            nativeCommand(['php',__FILE__,'cron-precheck',$run],$journal.'/cron-precheck.log');
            nativeCommand(['php','-f','/var/www/html/cron.php','--',CLEANUP_CLASS],$journal.'/cron.log');
            $result=['native_cron_exit_zero'=>true,'private_native_log'=>file_get_contents($journal.'/cron.log')]; break;
        case 'assert-restore':
            try { $result=assertion($journal); } finally {
                if (!is_file($journal.'/restored.json')) { restore($journal); }
            }
            break;
        case 'cleanup': restore($journal); $result=['cleanup_only'=>true]; break;
        default: throw new RuntimeException('unknown phase');
    }
    echo json_encode(['phase'=>$phase,'result'=>$result,'cgroups'=>cgroups()],JSON_THROW_ON_ERROR).PHP_EOL;
} catch (Throwable $e) {
    echo json_encode(['status'=>'BLOCKED_OR_FAILED','phase'=>substr($phase ?? '',0,64),'error_type'=>get_class($e),'private_error'=>privateError($e),'cgroups'=>cgroups()]).PHP_EOL;
    exit(1);
}
