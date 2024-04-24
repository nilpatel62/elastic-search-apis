from rest_framework.views import APIView
from django.http import HttpResponse, JsonResponse
from elastic_search_api_new.settings import es_url
import os, sys
import psutil
import docker
from bson.objectid import ObjectId
from datetime import datetime, timedelta
import time

# Define the index name
index_name = "filebeat-*"

# Function to calculate CPU percentage
def calculate_cpu_percent(d):
    print(d["cpu_stats"])
    try:
        cpu_count = d["cpu_stats"]["online_cpus"]
    except:
        cpu_count = 0
    cpu_percent = 0.0
    try:
        precpu_stats = float(d["precpu_stats"]["cpu_usage"]["total_usage"])
    except:
        precpu_stats = 0

    try:
        system_cpu_usage = float(d["precpu_stats"]["system_cpu_usage"])
    except:
        system_cpu_usage = 0


    cpu_delta = float(d["cpu_stats"]["cpu_usage"]["total_usage"]) - float(precpu_stats)
    system_delta = float(d["cpu_stats"]["system_cpu_usage"]) - system_cpu_usage

    print("system_delta", system_delta)
    print("cpu_delta", cpu_delta)

    if system_delta > 0.0 and cpu_delta > 0.0:
        try:
            cpu_percent = round((cpu_delta / system_delta) * cpu_count * 100.0, 2)
        except:
            cpu_percent = 0
    return cpu_percent


# Function to get network I/O
def get_network_io(d):
    networks = d["networks"] if "networks" in d else {}
    total_rx, total_tx = 0, 0
    for net in networks.values():
        total_rx += net["rx_bytes"]
        total_tx += net["tx_bytes"]
    return total_rx, total_tx

def get_memory_usage(container_stats):
    memory_usage = container_stats['memory_stats']['usage'] if "usage" in container_stats['memory_stats'] else 0
    max_memory = container_stats['memory_stats']['limit'] if "limit" in container_stats['memory_stats'] else 0
    memory_percent = (memory_usage / max_memory) * 100
    return memory_usage, memory_percent


# Create your views here.
class ElasticData(APIView):
    """
        API view for fetching data from Elasticsearch based on a search query.

        The view's `get` method accepts a `search` term, a `skip` parameter for pagination offset,
        and a `limit` parameter for the number of results to return. It builds an Elasticsearch query
        based on whether the `search` parameter is provided. If `search` is not empty, it adds a
        `match_phrase_prefix` filter to narrow the results to those where the 'hostname' field starts
        with the search term. The method then constructs an Elasticsearch query using the boolean `must`
        condition when there are search terms and handles pagination with `skip` and `limit`. The results
        are filtered to only include the ID and host fields from the source.

        If the Elasticsearch query returns results, the method packages these into a JSON response
        along with a success message. If no results are found, it returns a JSON response with an
        error message and a 404 status. Any exceptions in the process are caught, and an error message
        with a 500 status code is returned along with the error details.

        Attributes:
            es_url (Elasticsearch): The Elasticsearch connection used for making search queries.

        Methods:
            get(self, request, skip, limit, search): Processes the GET request to search data in Elasticsearch.
    """
    def get(self, request):
        try:
            size = int(request.GET.get("size", 10))
            page = int(request.GET.get("page", 0))
            search = request.GET.get("search", "")
            must_query = []
            if search != "":
                must_query.append({"match_phrase_prefix": {"hostname": search}})

            if len(must_query) == 0:
                search_query = {
                    "query": {
                        "match_all": {}
                    },
                    "size": size,
                    "from": page * 10,
                }
            else:
                search_query = {
                    "query": {
                        "bool": {
                            "must": must_query,
                            "minimum_should_match": 1,
                            "boost": 1.0,
                        }
                    },
                    "size": size,
                    "from": page * 10,
                }

            res_filter_parameters = es_url.search(
                index=index_name,
                body=search_query,
                filter_path=[
                    "hits.hits._id",
                    "hits.hits._source.host",
                ],
            )
            print(search_query)
            if len(res_filter_parameters) == 0:
                response = {"data": [], "message": "No Data Found"}
                return JsonResponse(response, safe=False, status=404)
            else:
                response_data = []
                for _res in res_filter_parameters['hits']['hits']:
                    response_data.append(
                        {
                            "id": _res['_id'],
                            "host": _res['_source']['host']
                        }
                    )
                response = {"data": response_data, "message": "Data Found"}
                return JsonResponse(response, safe=False, status=200)



        except Exception as ex:
            print("Error on line {}".format(sys.exc_info()[-1].tb_lineno), type(ex).__name__, ex)
            error = {
                "message": "something went wrong"
            }
            return JsonResponse(error, safe=False, status=500)


class SystemProcessData(APIView):
    def get(self, request):
        try:
            ## get the docker details
            client = docker.from_env()
            containers_info = []

            # System uptime
            uptime_seconds = datetime.now().timestamp() - psutil.boot_time()
            uptime = str(timedelta(seconds=int(uptime_seconds)))

            # Get details for each container
            containers_info = []
            for container in client.containers.list(all=True):
                stats = container.stats(stream=False)

                # Some stats may not be immediately available for new containers
                if 'precpu_stats' not in stats or not stats['precpu_stats']:
                    time.sleep(1)  # Wait a second before retrying
                    stats = container.stats(stream=False)

                try:
                    cpu_percent = calculate_cpu_percent(stats)
                except Exception as ex:
                    print("Error on line {}".format(sys.exc_info()[-1].tb_lineno), type(ex).__name__, ex)
                    cpu_percent = 0
                memory_usage = stats["memory_stats"]["usage"] if "usage" in stats['memory_stats'] else 0
                memory_limit = stats["memory_stats"]["limit"] if "limit" in stats['memory_stats'] else 0
                net_rx, net_tx = get_network_io(stats)
                try:
                    block_read, block_write = stats["blkio_stats"]["io_service_bytes_recursive"][0]["value"], \
                                              stats["blkio_stats"]["io_service_bytes_recursive"][1]["value"]
                except:
                    block_read, block_write = 0, 0
                pids = stats["pids_stats"]["current"] if "current" in stats["pids_stats"] else 0
                name = container.name
                id = container.id
                # Get container status
                status = container.status

                # Get IP address
                ip_address = container.attrs['NetworkSettings']['IPAddress']
                if not ip_address:  # IPAddress might be an empty string if the container is not using the default bridge network
                    # If the container is connected to a user-defined network, fetch the IP from the Networks section
                    networks = container.attrs['NetworkSettings']['Networks']
                    if networks:
                        # Get the IP address from the first available network
                        ip_address = list(networks.values())[0]['IPAddress']

                containers_info.append({
                    'name': f"{name}",
                    'status': f"{status}",
                    "id": f"{id}",
                    'cpu_percent': f"{cpu_percent}",
                    'memory_usage': f"{memory_usage / (1024 ** 3):.2f}GiB",
                    'memory_limit': f"{memory_limit / (1024 ** 3):.2f}GiB",
                    'net_io': f"{net_rx / (1024 ** 2):.2f}MB / {net_tx / (1024 ** 2):.2f}MB",
                    'block_io': f"{block_read / (1024 ** 2):.2f}MB / {block_write / (1024 ** 2):.2f}MB",
                    'pids': pids,
                    "ip_address": ip_address
                })

            response = {"data": containers_info, "message": "Data Found", "system_up_time": uptime}
            return JsonResponse(response, safe=False, status=200)



        except Exception as ex:
            print("Error on line {}".format(sys.exc_info()[-1].tb_lineno), type(ex).__name__, ex)
            error = {
                "message": "something went wrong"
            }
            return JsonResponse(error, safe=False, status=500)


    def post(self, request):
        try:
            data = request.data

            if len(data) == 0:
                error = {
                    "message": "request body is missing"
                }
                return JsonResponse(error, safe=False, status=400)

            ## get the docker details
            client = docker.from_env()
            containers_info = data['container_ids']
            for _ids in containers_info:
                try:
                    # Find the container by name
                    container = client.containers.get(_ids)
                    print(f"Restarting container: {container.name}")
                    container.restart()  # Restart the container
                    print(f"Container {container.name} has been restarted successfully.")
                except docker.errors.NotFound:
                    print(f"No container with the id '{_ids}' was found.")
                except docker.errors.APIError as e:
                    print(f"An error occurred while trying to restart the container '{_ids}': {e}")

            response = {
                "message": "Successfully restarted"
            }
            return JsonResponse(response, safe=False, status=200)

        except Exception as ex:
            print("Error on line {}".format(sys.exc_info()[-1].tb_lineno), type(ex).__name__, ex)
            error = {
                "message": "something went wrong"
            }
            return JsonResponse(error, safe=False, status=500)


class SystemData(APIView):

    def post(self, request):
        try:
            parent_product_id = str(ObjectId())
            data = request.data
            current = datetime.now()
            str_date = datetime.strftime(current, "%Y.%m.%d")
            data_add_index = "filebeat-8.13.2-"+str_date+"-000001"

            if len(data) == 0:
                error = {
                    "message": "request body is missing"
                }
                return JsonResponse(error, safe=False, status=400)

            es_url.index(index=data_add_index, id=str(parent_product_id), body=data)

            response = {
                "message": "Successfully Added the data"
            }
            return JsonResponse(response, safe=False, status=200)

        except Exception as ex:
            print("Error on line {}".format(sys.exc_info()[-1].tb_lineno), type(ex).__name__, ex)
            error = {
                "message": "something went wrong"
            }
            return JsonResponse(error, safe=False, status=500)