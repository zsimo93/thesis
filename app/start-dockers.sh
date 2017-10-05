echo "Enter role [ENTER]:"
read role
export TH_ROLE=$role

docker run --name mongoDB --network host -d zsimo/rpi-mongo --replSet foo

echo "Enter MASTER IP [ENTER]:"
read ip
export TH_MASTERIP=$ip

echo "Enter name for node [ENTER]:"
read name
export TH_NODENAME=$name

export BASE_DIR=`pwd`

if [ "$TH_ROLE" = "MASTER" ]; then
    echo "running Master"
else
    echo "Enter local ip [ENTER]:"
    read localip
    curl -i \
        -H "Accept: application/json" \
        -H "Content-Type:application/json" \
        -X POST --data '{"type": "node", "setup": false, "ip": '"$localip"'", "architecture": "arm", "name": '"$name"'", "role": "NODE" }' \
        "$ip:8080/api/nodes"
fi

python main_docker.py &
gunicorn mainAPI:app -b 0.0.0.0:8080 --threads=100 -t 100

docker stop mongoDB
docker rm mongoDB
pkill -f main_docker.py
