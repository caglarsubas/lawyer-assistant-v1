#!/bin/sh
set -eu
# The bootstrap alone gets NET_ADMIN. No server starts until a fail-closed
# firewall is installed. DNS is used once, then all DNS egress is closed.
iptables -P OUTPUT DROP
iptables -P INPUT DROP
iptables -P FORWARD DROP
ip6tables -P OUTPUT DROP
ip6tables -P INPUT DROP
ip6tables -P FORWARD DROP
iptables -F OUTPUT
iptables -F INPUT
iptables -A OUTPUT -o lo -j ACCEPT
iptables -A INPUT -i lo -j ACCEPT
provider_target="$(python /app/relay.py --resolve)"
# --resolve emits only one validated IPv4 and port. No shell evaluation.
set -- $provider_target
test "$#" -eq 2
provider_ip="$1"
provider_port="$2"
test -n "$provider_ip"
case "$provider_port" in
  443) export PROVIDER_TUNNEL_IP="$provider_ip" ;;
  8080) export PROVIDER_NATIVE_IP="$provider_ip" ;;
  *) exit 1 ;;
esac
iptables -A OUTPUT -d "$provider_ip" -p tcp --dport "$provider_port" -j ACCEPT
iptables -A INPUT -s "$provider_ip" -p tcp --sport "$provider_port" -m conntrack --ctstate ESTABLISHED -j ACCEPT
# Match the dedicated internal provider network. Never attach this relay to
# private database/document networks, and never publish its service port.
iptables -A INPUT -s 172.30.240.0/28 -p tcp --dport 8083 -j ACCEPT
iptables -A OUTPUT -d 172.30.240.0/28 -p tcp --sport 8083 -m conntrack --ctstate ESTABLISHED -j ACCEPT
iptables -D OUTPUT -o lo -j ACCEPT
iptables -D INPUT -i lo -j ACCEPT
iptables -A OUTPUT -o lo -d 127.0.0.1 -p tcp --dport 8083 -j ACCEPT
iptables -A INPUT -i lo -d 127.0.0.1 -p tcp --dport 8083 -j ACCEPT
iptables -A OUTPUT -o lo -d 127.0.0.1 -p tcp --sport 8083 -m conntrack --ctstate ESTABLISHED -j ACCEPT
iptables -A INPUT -i lo -s 127.0.0.1 -p tcp --sport 8083 -m conntrack --ctstate ESTABLISHED -j ACCEPT
exec gosu relay:relay python /app/relay.py
