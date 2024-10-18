import urllib3
import boto3
import os
import json

http = urllib3.PoolManager()
cloudwatch = boto3.client(
    'cloudwatch',
    region_name='us-east-1'
)


def lambda_handler(event, context):
    rabbitmq_user = os.getenv('User')
    rabbitmq_password = os.getenv('Password')
    node = os.getenv('Node')
    env = os.getenv('Env')
    headers = urllib3.make_headers(basic_auth=f'{rabbitmq_user}:{rabbitmq_password}')
    try:
        node_aliveness_response = http.request(
            'GET',
            f'http://{node}.{env}:15672/api/aliveness-test/%2F',
            headers=headers,
            timeout=0.2,
            retries=False
        )
    except Exception:
        return
    node_count = 0
    if (
        node_aliveness_response is not None
        and node_aliveness_response.status == 200
    ):
        node_count = 1
    # The following metric will be used to know whether a RabbitMQ Node is alive or dead
    cloudwatch.put_metric_data(
        MetricData=[
            {
                'MetricName': 'Node Health Check',
                'Dimensions': [
                    {
                        'Name': 'Node',
                        'Value': node
                    },
                    {
                        'Name': 'Environment',
                        'Value': env
                    }
                ],
                'Unit': 'Count',
                'Value': node_count
            }
        ],
        Namespace='RabbitMQNodes'
    )
    cluster_nodes_count = 0
    try:
        cluster_info_response = http.request(
            'GET',
            f'http://{node}.{env}:15672/api/vhosts',
            headers=headers,
            timeout=0.2,
            retries=False
        )
    except Exception:
        return
    if (
        cluster_info_response is not None
        and cluster_info_response.data is not None
        and cluster_info_response.status == 200
    ):
        cluster_info = json.loads(cluster_info_response.data)[0]['cluster_state']
        if cluster_info is not None:
            for value in cluster_info.values():
                if value == 'running':
                    cluster_nodes_count += 1
    # The following metric will be used to know the number of Nodes
    # that are in cluster with/including current RabbitMQ Node
    cloudwatch.put_metric_data(
        MetricData=[
            {
                'MetricName': 'Cluster Health Check - Active Nodes In Cluster',
                'Dimensions': [
                    {
                        'Name': 'Node',
                        'Value': node
                    },
                    {
                        'Name': 'Environment',
                        'Value': env
                    }
                ],
                'Unit': 'Count',
                'Value': cluster_nodes_count
            }
        ],
        Namespace='RabbitMQNodes'
    )
