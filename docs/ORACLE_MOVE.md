# Move GiveLife studio from Render to Oracle Cloud (Always Free, ARM)

Simple rules: **one server at a time**. Never paste secrets in chat. You click on websites; commands are in boxes.

## What was decided (and why)
- **Server:** Oracle `VM.Standard.A1.Flex` (ARM64), **2 CPU, 6 GB RAM**, Ubuntu 24.04. Free, much stronger than Render's 512 MB.
- **ARM gateway:** the official GoWA v9.7.0 **arm64** zip exists. The 45 s -> 300 s patch was found in the arm64 file (offset `0xAECC38`, function `cmd.restServer`, the same place as the amd64 patch). `scripts/patch_gowa_arm64.py` checks the exact bytes and **fails the build** if the file is different. `Dockerfile.arm64` is separate; `Dockerfile` (Render) is unchanged.
- **HTTPS:** Caddy + a free DuckDNS name. Fixed address, free, only ports 80 and 443 open. (Cloudflare Tunnel needs a domain you own; its free "quick" address changes on every restart.)
- **One WhatsApp owner:** `REQUIRE_WA_LEASE=1` makes the Oracle app **refuse to start** if Render still holds the WhatsApp lease. Render does not use this setting.
- **Always on:** Docker `restart: unless-stopped`; 3 GB memory cap; waits 200 s on stop so a person in the middle of DMs finishes.

## Oracle's idle rule (checked on Oracle's own page)
Oracle may take back a free server if, for 7 days, **all three** are true: CPU (95th percentile) < 20%, network < 20%, **and** memory < 20% (A1 only). Your app uses little CPU, so it may look idle on CPU and network. That is why we pick **6 GB** (not 24 GB): the app + Docker + system use roughly 1 to 1.5 GB, about 17 to 25% of 6 GB. **I am not sure** it stays above 20%. After 2 days run `free -m` and look at Oracle's graphs (Compute > your server > Metrics). If memory is under 20%, tell me: we lower the server to 4 GB (can be done in Oracle in 2 clicks). Source: https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm

## Part 1. Oracle website
1. Sign up at https://www.oracle.com/cloud/free/ (needs a card for identity check; Always Free is not charged). **Your home region cannot be changed later.** Check where your Supabase database is (Supabase > Project Settings) and pick the nearest Oracle region if you can.
2. Menu > **Compute > Instances > Create instance**.
   - Name: `givelife`
   - Image: **Canonical Ubuntu 24.04** (pick the one for Ampere/aarch64)
   - Shape: **Ampere > VM.Standard.A1.Flex**, **2 OCPU, 6 GB**
   - Networking: keep default, **Assign public IPv4 address = yes**
   - SSH keys: **Generate a key pair**, download BOTH files, keep them safe (the private key is your only door in)
   - Boot volume: 50 GB
   - Click **Create**. If it says "Out of capacity", try again later or in another availability domain (common on free ARM).
3. Open the instance page and copy the **Public IP address** (you will need it twice).
4. Open the web ports: instance page > **Subnet** link > **Default Security List** > **Add Ingress Rules**: Source CIDR `0.0.0.0/0`, protocol TCP, destination port `80`. Add a second rule for port `443`.

## Part 2. DuckDNS (free name)
1. Go to https://www.duckdns.org and sign in. Make a name, for example `givelife-studio`. Put the Oracle public IP in "current ip". Press update.
2. Your address is `givelife-studio.duckdns.org`. (Keep your DuckDNS token private.)

## Part 3. Server setup (PowerShell on your PC)
Connect (change the path and IP):
```
ssh -i C:\path\to\your-private.key ubuntu@PUBLIC_IP
```
Then on the server:
```
sudo apt-get update && sudo apt-get -y upgrade
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
sudo apt-get install -y git iptables-persistent
sudo iptables -I INPUT 1 -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 1 -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
exit
```
Connect again (so Docker works without sudo). Oracle's Ubuntu image blocks ports in its own firewall too; the two `iptables` lines open them. (I could not test this part from my PC.)

## Part 4. Get the app
The Oracle files are on branch `oracle-arm64` (not merged to main yet). On the server:
```
git clone -b oracle-arm64 https://github.com/wajhansx-png/givelife-message-studio.git
cd givelife-message-studio/deploy/oracle
cp env.example .env
chmod 600 .env
nano .env
```
In `nano`: write your DuckDNS name after `DOMAIN=`. Copy each value from the **Render dashboard > your service > Environment** straight into this file (DB_URI, UI_ACCESS_KEY, DEEPSEEK_API_KEY, and every other variable you see there except PORT and DATA_DIR). Save: Ctrl+O, Enter, Ctrl+X.

## Part 5. Build and test (Render still running, nothing starts yet)
```
docker compose build
docker compose run --rm --no-deps --entrypoint /usr/local/bin/whatsapp app --help
```
The build takes several minutes. The second command only checks that the ARM gateway program opens. It sends nothing and does not start the app.

## Part 6. STOP RENDER NOW
Render dashboard > your service > **Settings > Suspend Service**. Wait until it says **Suspended**. **Tell me when it is done.** Do not go on before that. Two servers on the same WhatsApp numbers means double or lost messages.

## Part 7. Start on Oracle
```
docker compose up -d
docker compose logs -f app
```
Look for `WhatsApp lease: acquired`. (Stop the log with Ctrl+C; the app keeps running.) If you see `lease not acquired`, Render is still running: stop it and run `docker compose up -d` again.
Then open `https://YOUR-NAME.duckdns.org` in your phone. The first visit waits about a minute while Caddy gets the free certificate.

## Part 8. Checklist (tell me each result)
- [ ] The site opens on your phone and asks for the access key
- [ ] All 3 WhatsApps show **connected** (main, Giki, Giki 2). If one says disconnected, scan its QR again
- [ ] `/giki` and `/giki2` pages load
- [ ] `docker stats --no-stream` : app memory is OK (well under 3 GB)
- [ ] Reboot test: `sudo reboot`, wait 3 minutes, the site comes back by itself
- [ ] You test one message yourself (I never send)

## Update later (one command)
```
cd ~/givelife-message-studio/deploy/oracle && ./update.sh
```
**Never update while DMs are sending.** A restart can cut a person in the middle of their messages. Stop DMs or wait for the batch to finish first.

## Go back to Render
1. On the server: `cd ~/givelife-message-studio/deploy/oracle && docker compose stop` (takes up to 3 minutes; wait until the prompt returns).
2. Render dashboard > **Resume Service**. Wait until live.
Never have both running.

## Things I am not sure about
- I could not build or run the ARM image on my PC (no Docker here). I checked the gateway patch by reading the real arm64 file, not by running it. The first `docker compose build` on the server is the real test.
- Whether the patched ARM instruction fully acts like the amd64 one for the 300 s limit. Group sends after a restart are the thing to watch.
- The WhatsApp links may need a QR scan again after the move.
- Oracle can change its free rules. Re-read the idle rule page now and then.
- `ALLOWED_ORIGINS` on Render points to another website address. If you still use that address, it will not reach the Oracle server unless that site is changed too.
