import requests
import sys

payload = {
	"type": "node",
	"setup": False,
	"ip": sys.argv[2],
	"architecture": "arm",
	"name": sys.argv[3],
	"role": "NODE" }

r = requests.post(sys.argv[1], json=payload)
print r.text
