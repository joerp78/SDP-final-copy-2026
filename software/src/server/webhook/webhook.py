import hmac
import hashlib
import subprocess
import os
from flask import Flask, request, jsonify

app = Flask(__name__)
SECRET = os.environ.get('WEBHOOK_SECRET', '').encode()

@app.route('/deploy', methods=['POST'])
def deploy():
    sig = request.headers.get('X-Hub-Signature-256', '')
    expected = 'sha256=' + hmac.new(SECRET, request.data, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(sig, expected):
        return jsonify({'error': 'Unauthorized'}), 401

    subprocess.Popen(['/opt/sdp/deploy.sh'])
    return jsonify({'status': 'Deploy triggered'}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9000)