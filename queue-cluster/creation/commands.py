from argparse import ArgumentParser
import os
import time
from typing import List
import requests
import json
import shutil
import boto3


def update_node_service_discovery_mapping(env, node):
    instance_ip_request = requests.get("http://instance-data/latest/meta-data/local-ipv4")
    instance_private_ipv4_address = instance_ip_request.text
    servicediscovery = boto3.client(
        'servicediscovery',
        region_name='us-east-1'
    )
    all_namespaces = servicediscovery.list_namespaces(
        Filters=[
            {
                'Name': 'TYPE',
                'Values': [
                    'DNS_PRIVATE',
                ],
                'Condition': 'EQ'
            },
        ]
    )
    namespace_id = [namespace for namespace in all_namespaces['Namespaces'] if namespace['Name'] == env][0]['Id']
    all_services = servicediscovery.list_services(
        Filters=[
            {
                'Name': 'NAMESPACE_ID',
                'Values': [
                    namespace_id,
                ],
                'Condition': 'EQ'
            },
        ]
    )
    service_id = [service for service in all_services['Services'] if service['Name'] == node][0]['Id']
    response = servicediscovery.register_instance(
        ServiceId=service_id,
        InstanceId='Node',
        Attributes={
            'AWS_INSTANCE_IPV4': instance_private_ipv4_address
        }
    )
    print(response)


def execute_command(command):
    os.system(command)


def execute_rabbitmq_commands(rabbitmq_commands: List[str]):
    for rabbitmq_command in rabbitmq_commands:
        execute_command(
            'docker exec rabbit-node {command}'.format_map({
                'command': rabbitmq_command
            })
        )


def prepare_rabbitmq_configuration_file(env, nodes):
    shutil.copyfile('rabbitmq_template.conf', 'rabbitmq.conf')
    rabbitmq_conf_file = open('rabbitmq.conf', 'a')
    for index, node in enumerate(nodes):
        rabbitmq_conf_file.write(
            f'cluster_formation.classic_config.nodes.{index+1} = rabbit@{nodes[node]}.{env} \n'
        )
    rabbitmq_conf_file.close()
    print('\n---rabbitmq.conf---\n')
    final_configuration = open("rabbitmq.conf", "r").read()
    print(final_configuration)


def set_policy(env, nodes):
    nodes_list = [f'rabbit@{nodes["node1"]}.{env}', f'rabbit@{nodes["node2"]}.{env}', f'rabbit@{nodes["node3"]}.{env}']
    print('\n---Setting queue mirroring and auto-sync policy---\n')
    federation_policy = json.dumps({
        "federation-upstream-set": "all",
        "ha-sync-mode": "automatic",
        "ha-mode": "nodes",
        "ha-params": nodes_list
    })
    os.system(
        '''{exec_command} set_policy ha-fed ".*" '{policy}' --priority 1 --apply-to queues'''.format_map({
            'exec_command': 'docker exec rabbit-node rabbitmqctl',
            'policy': federation_policy
        })
    )


def create_an_admin_user(rabbitmq_user_details):
    print("\n---Creating a new admin user and deleting default guest user---\n")
    username = rabbitmq_user_details.get('username')
    password = rabbitmq_user_details.get('password')
    execute_rabbitmq_commands(
        rabbitmq_commands=[
            f'rabbitmqctl add_user {username} {password}',
            f'rabbitmqctl set_user_tags {username} administrator',
            f'rabbitmqctl set_permissions -p / {username} ".*" ".*" ".*"',
            'rabbitmqctl delete_user guest'
        ]
    )


def perform_operations_on_node_start(config):
    create_an_admin_user(config.get('rabbitmq_user_details'))
    set_policy(config.get('env'), config.get('nodes'))


def wait_for_rabbit_node_to_start(func, config, max_limit=15):
    max_time_to_wait = max_limit
    try:
        time.sleep(0.5)
        max_time_to_wait = max_time_to_wait - 0.5
        requests.get("http://guest:guest@localhost:15672/api/aliveness-test/%2F")
        func(config)
    except Exception as e:
        if max_time_to_wait > 0:
            wait_for_rabbit_node_to_start(func, config, max_limit=max_time_to_wait)
        else:
            raise e


def start_node(env, current_node, rabbitmq_user_details, erlang_cookie, all_nodes):
    print('\n---Updating service discovery mapping ---\n')
    update_node_service_discovery_mapping(env, current_node)
    print('\n---Starting node ', current_node, ' ---\n')
    prepare_rabbitmq_configuration_file(env, all_nodes)
    print('\n---Starting rabbitmq docker container---\n')
    execute_command(
        'docker run -d \
        --network host \
        --restart always \
        -v {PWD}/:/config/ \
        -e RABBITMQ_CONFIG_FILE=/config/rabbitmq \
        -e RABBITMQ_ERLANG_COOKIE={erlang_cookie} \
        -e RABBITMQ_USE_LONGNAME=true \
        --hostname {hostname} \
        --name rabbit-node \
        rabbitmq:3.10.5-management'
        .format_map({
            'PWD': os.getcwd(),
            'erlang_cookie': erlang_cookie,
            'hostname': f'{current_node}.{env}'
        })
    )
    print('\n---Enabling federation plugin---\n')
    execute_rabbitmq_commands(
        rabbitmq_commands=[
            'rabbitmq-plugins enable rabbitmq_federation'
        ]
    )
    print('\n---Waiting for the rabbitmq node to start---\n')
    wait_for_rabbit_node_to_start(
        perform_operations_on_node_start,
        {
            'rabbitmq_user_details': rabbitmq_user_details,
            'nodes': all_nodes,
            'env': env
        },
        max_limit=20
    )


def stop_node():
    print('\n---Stopping the rabbitmq node---\n')
    execute_command('docker stop rabbit-node &&  docker rm rabbit-node')


def watch_node():
    execute_command('docker logs -f rabbit-node')


def bash_node():
    execute_command('docker exec -it rabbit-node bash')


if __name__ == '__main__':
    parser = ArgumentParser(description='A command line tool for deploying rabbitmq cluster')
    parser.add_argument(
        '--start_node',
        nargs=7,
        help='Starts a rabbitmq node.',
        metavar=('ENV', 'CurrentNode', 'User', 'Password', 'Cookie', 'Node2', 'Node3')
    )
    parser.add_argument('--stop_node', action='store_true', help='Stops a rabbitmq node.')
    parser.add_argument('--watch_node', action='store_true', help='Watch logs of rabbitmq node.')
    parser.add_argument('--bash_node', action='store_true', help='Go into shell of rabbitmq node.')

    args = parser.parse_args()
    if args.start_node is not None and len(args.start_node) == 7:
        start_node(
            env=args.start_node[0],
            current_node=args.start_node[1],
            rabbitmq_user_details={
                'username': args.start_node[2],
                'password': args.start_node[3]
            },
            erlang_cookie=args.start_node[4],
            all_nodes={
                'node1': args.start_node[1],
                'node2': args.start_node[5],
                'node3': args.start_node[6]
            }
        )
    elif args.stop_node:
        stop_node()
    elif args.watch_node:
        watch_node()
    elif args.bash_node:
        bash_node()
    else:
        print('Use the -h or --help flags for help')
