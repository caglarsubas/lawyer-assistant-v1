#!/bin/sh
set -eu
# Docker Desktop cannot publish ports from an internal-only network. The web
# edge has an ingress network, but may initiate traffic only to the local API.
# Install a default-deny policy before starting nginx; any failure aborts boot.
iptables -P OUTPUT DROP
iptables -F OUTPUT
iptables -A OUTPUT -o lo -j ACCEPT
iptables -A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
api_ip="$(getent hosts api | awk 'NR == 1 {print $1}')"
test -n "$api_ip"
iptables -A OUTPUT -d "$api_ip" -p tcp --dport 8000 -j ACCEPT
# Resolve the fixed upstream once, then close Docker's DNS forwarding path.
sed "s|http://api:8000|http://$api_ip:8000|" /etc/nginx/nginx.conf > /tmp/nginx.conf
iptables -D OUTPUT -o lo -j ACCEPT
iptables -A OUTPUT -o lo -d 127.0.0.1 -p tcp --dport 80 -j ACCEPT
exec su-exec nginx:nginx nginx -e stderr -c /tmp/nginx.conf -g 'daemon off;'
