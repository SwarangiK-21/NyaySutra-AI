#!/usr/bin/env bash
# One-time preparation of a fresh Oracle Cloud Ubuntu 24.04 (ARM, Ampere A1) server for NyaySutra AI.
# Run on the server as the default "ubuntu" user:   bash setup-server.sh
# Safe to run again. It does NOT copy secrets or start the app — see docs/DEPLOY_ORACLE.md.
set -euo pipefail

echo "== 1/6 System updates"
sudo apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y git curl ca-certificates unattended-upgrades netfilter-persistent

echo "== 2/6 Automatic security updates"
sudo dpkg-reconfigure -f noninteractive unattended-upgrades

echo "== 3/6 Firewall: allow web traffic (Oracle's Ubuntu images block it in iptables by default)"
for port in 80 443; do
  if ! sudo iptables -C INPUT -p tcp --dport "$port" -m state --state NEW -j ACCEPT 2>/dev/null; then
    # Insert before Oracle's final REJECT rule so the port is actually reachable.
    sudo iptables -I INPUT 6 -p tcp --dport "$port" -m state --state NEW -j ACCEPT
  fi
done
sudo iptables -C INPUT -p udp --dport 443 -j ACCEPT 2>/dev/null || sudo iptables -I INPUT 6 -p udp --dport 443 -j ACCEPT  # HTTP/3
sudo netfilter-persistent save

echo "== 4/6 Docker (official install script) with log rotation"
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh
fi
sudo mkdir -p /etc/docker
echo '{"log-driver": "json-file", "log-opts": {"max-size": "20m", "max-file": "3"}}' | sudo tee /etc/docker/daemon.json >/dev/null
sudo systemctl restart docker
sudo usermod -aG docker "$USER"

echo "== 5/6 Get the code"
if [ ! -d "$HOME/nyaysutra/.git" ]; then
  git clone https://github.com/SwarangiK-21/NyaySutra-AI.git "$HOME/nyaysutra"
fi
echo "   (switch branch later with: cd ~/nyaysutra && git checkout <branch> && git pull)"

echo "== 6/6 Check"
docker --version
uname -m
free -h | head -2
echo
echo "Done. Log out and back in (so 'docker' works without sudo), then continue with docs/DEPLOY_ORACLE.md step 6."
