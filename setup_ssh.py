import os
import paramiko

key_file = os.path.expanduser('~/.ssh/id_rsa')
pub_key_file = key_file + '.pub'

# Generate key if not exists
if not os.path.exists(key_file):
    if not os.path.exists(os.path.dirname(key_file)):
        os.makedirs(os.path.dirname(key_file))
    print("Generating new RSA key...")
    key = paramiko.RSAKey.generate(2048)
    key.write_private_key_file(key_file)
    with open(pub_key_file, 'w') as f:
        f.write(f"{key.get_name()} {key.get_base64()} antigravity@local\n")
else:
    print("Key already exists.")

# Read public key
with open(pub_key_file, 'r') as f:
    pub_key = f.read().strip()

# Connect via password and add key
print("Connecting to Hostinger...")
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('82.198.227.73', port=65002, username='u793694890', password='sUJxYH4LBTLC&')

print("Adding SSH key to authorized_keys...")
stdin, stdout, stderr = client.exec_command('mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo "' + pub_key + '" >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys')
print(stdout.read().decode())
print(stderr.read().decode())
client.close()
print("Success! Passwordless SSH is now configured.")
