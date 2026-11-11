#!/usr/bin/env bash
# Deliberately one service at a time. A lease is a coordinator authorization, not a lock.
set -euo pipefail
usage() { echo 'Usage: talos-proof-media-batch.sh start|stop SERVICE PRIVATE_STATE_DIR' >&2; exit 2; }
[[ $# == 3 ]] || usage
: "${KUBECONFIG:?explicit proof kubeconfig required}"
: "${TALOS_PROOF_MEDIA_LEASE:?coordinator must grant a current live resource lease first}"
action=$1 service=$2 state=$3
root=$(cd "$(dirname "$0")/.." && pwd)
case "$service" in radarr|sonarr|lidarr|prowlarr|qbittorrent|qbitwebui|sabnzbd|plex|tautulli|seerr|jellyfin|audiobookshelf|pinchflat) ;; *) usage;; esac
ns=proof-$service
case "$action" in
  start)
    # Refuse a second media batch; a coordinator can explicitly arrange helper dependency experiments.
    active=$(kubectl get deployments -A -l app.kubernetes.io/part-of=talos-proof -o json | python3 -c 'import json,sys; print(sum(x["spec"].get("replicas",1) for x in json.load(sys.stdin)["items"] if x["metadata"]["namespace"].startswith("proof-") and x["metadata"]["name"] in "radarr sonarr lidarr prowlarr qbittorrent qbitwebui sabnzbd plex tautulli seerr jellyfin audiobookshelf pinchflat".split()))')
    [[ "$active" == 0 ]] || { echo 'Stop the active media batch before starting another.' >&2; exit 1; }
    [[ -f "$state/$service-secret.json" ]] || { echo 'Generate private bootstrap state first.' >&2; exit 1; }
    kubectl apply -k "$root/kubernetes/apps/media/$service"
    kubectl apply -f "$state/$service-secret.json" >/dev/null
    kubectl -n "$ns" scale deployment "$service" --replicas=1
    kubectl -n "$ns" rollout status deployment/"$service" --timeout=300s
    echo 'Startup only; functional acceptance still requires the service-specific test.'
    ;;
  stop)
    kubectl -n "$ns" scale deployment "$service" --replicas=0
    kubectl -n "$ns" wait --for=delete pod -l "app.kubernetes.io/name=$service" --timeout=120s
    ;;
  *) usage;;
esac
