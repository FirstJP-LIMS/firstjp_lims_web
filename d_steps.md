Sevenwings Incorporated
Django AWS-EC2 Multi-Tenant Deployment Guide
Phase 1: Environment Setup
First, prepare the server and pull your code.
Update System & Install Dependencies:
Bash
sudo apt update
sudo apt install python3-venv python3-pip nginx git -y


Clone Repository:
Bash
git clone repo-url.git
cd web_app


Virtual Environment & Requirements:
Bash
python3 -m venv virt
source virt/bin/virt/activate
pip install -r requirements.txt
pip install gunicorn


Phase 2: Gunicorn Configuration
Gunicorn acts as the Application Server. We use a Socket to allow Nginx to communicate with it efficiently.
1. Create the Gunicorn Socket:
sudo nano /etc/systemd/system/gunicorn.socket

Ini, TOML

[Unit]
Description=gunicorn socket

[Socket]
ListenStream=/run/gunicorn.sock
SocketUser=www-data
SocketGroup=www-data
SocketMode=0660

[Install]
WantedBy=sockets.target


2. Create the Gunicorn Service:
sudo nano /etc/systemd/system/gunicorn.service

Ini, TOML

[Unit]
Description=gunicorn daemon
Requires=gunicorn.socket
After=network.target

[Service]
User=ubuntu
Group=www-data
# Navigate to root directory where manage.py is located
WorkingDirectory=/home/ubuntu/firstjp_lims_web
# Virtual environment
ExecStart=/home/ubuntu/virt/bin/gunicorn \
    --access-logfile - \
    --workers 3 \
    --bind unix:/run/gunicorn.sock \
    lims_auth.wsgi:application  # Project folder

[Install]
WantedBy=multi-user.target




3. Start and Enable Services:
Bash
sudo systemctl daemon-reload
sudo systemctl start gunicorn.socket
sudo systemctl enable gunicorn.socket
sudo systemctl status gunicorn.socket


Phase 3: Nginx Configuration (The Multi-Tenant Gateway)
Nginx handles incoming traffic and routes it to Gunicorn. The wildcard *.medvuno.com is essential for multi-tenancy.
1. Create Site Configuration:
sudo nano /etc/nginx/sites-available/web_conf
Nginx
server {
    listen 80;
    server_name medvuno.com *.medvuno.com;
    return 301 https://$host$request_uri; # Redirect HTTP to HTTPS
}

server {
    listen 443 ssl;
    server_name medvuno.com *.medvuno.com;

    ssl_certificate /etc/letsencrypt/live/medvuno.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/medvuno.com/privkey.pem;

    location /static/ {
        alias /home/ubuntu/firstjp_lims_web/staticfiles/;
        expires 30d;
    }

    location /media/ {
        alias /home/ubuntu/firstjp_lims_web/media/;
    }

    location / {
        include proxy_params;
        proxy_pass http://unix:/run/gunicorn.sock;
        
        # Crucial for Multi-Tenancy
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}


2. Enable Configuration & Permissions:

Bash


# Link to enabled sites
sudo ln -s /etc/nginx/sites-available/firstjp_lims /etc/nginx/sites-enabled

# Fix permissions so Nginx can read your files
sudo chmod +x /home/ubuntu
sudo chmod +x /home/ubuntu/firstjp_lims_web
sudo chmod -R 755 /home/ubuntu/firstjp_lims_web/staticfiles

# Test and Restart
sudo nginx -t
sudo systemctl restart nginx


Phase 4: SSL (Let's Encrypt)
Since you are using a wildcard *.medvuno.com, you usually need a DNS-01 challenge for Certbot.
Install Certbot:
Bash
sudo apt install certbot python3-certbot-nginx


Generate Certificate:
Bash
sudo certbot certonly --manual -d medvuno.com -d *.medvuno.com --preferred-challenges dns
Note: Follow the prompts to add the required TXT records to your DNS provider (Route53, Cloudflare, etc.).
🛠️ Troubleshooting & Maintenance Commands
Task
Command
Check Gunicorn Logs
sudo journalctl -u gunicorn
Check Nginx Logs
sudo tail -f /var/log/nginx/error.log
Restart Gunicorn
sudo systemctl restart gunicorn
Check Socket Status
file /run/gunicorn.sock


