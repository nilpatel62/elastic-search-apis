from rest_framework.views import APIView
from django.http import HttpResponse, JsonResponse
from elastic_search_api_new.settings import es_url
import os, sys
import psutil
import docker
from datetime import datetime, timedelta
import time


# Function to calculate CPU percentage
def calculate_cpu_percent(d):
    try:
        cpu_count = len(d["cpu_stats"]["cpu_usage"]["percpu_usage"])
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
    if system_delta > 0.0 and cpu_delta > 0.0:
        try:
            cpu_percent = (cpu_delta / system_delta) * cpu_count * 100.0
        except:
            cpu_percent = 0
    return cpu_percent


# Function to get network I/O
def get_network_io(d):
    networks = d["networks"]
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
            # Define the index name
            index_name = "filebeat-*"

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
                try:
                    cpu_percent = calculate_cpu_percent(stats)
                except:
                    cpu_percent = 0
                memory_usage = stats["memory_stats"]["usage"]
                memory_limit = stats["memory_stats"]["limit"]
                net_rx, net_tx = get_network_io(stats)
                block_read, block_write = stats["blkio_stats"]["io_service_bytes_recursive"][0]["value"], \
                                          stats["blkio_stats"]["io_service_bytes_recursive"][1]["value"]
                pids = stats["pids_stats"]["current"]
                name = container.name

                containers_info.append({
                    'name': name,
                    'cpu_percent': cpu_percent,
                    'memory_usage': memory_usage,
                    'memory_limit': memory_limit,
                    'net_io': (net_rx, net_tx),
                    'block_io': (block_read, block_write),
                    'pids': pids
                })

            # Print formatted stats like the docker stats command
            print(f"{'NAME':<15} {'CPU %':<10} {'MEM USAGE / LIMIT':<20} {'NET I/O':<20} {'BLOCK I/O':<15} {'PIDS':<5}")
            for info in containers_info:
                mem_usage_limit = f"{info['memory_usage'] / (1024 ** 3):.2f}GiB / {info['memory_limit'] / (1024 ** 3):.2f}GiB"
                net_io = f"{info['net_io'][0] / (1024 ** 2):.2f}MB / {info['net_io'][1] / (1024 ** 2):.2f}MB"
                block_io = f"{info['block_io'][0] / (1024 ** 2):.2f}MB / {info['block_io'][1] / (1024 ** 2):.2f}MB"
                print(
                    f"{info['name']:<15} {info['cpu_percent']:<10.2f} {mem_usage_limit:<20} {net_io:<20} {block_io:<15} {info['pids']:<5}")

            response = {"data": containers_info, "message": "Data Found", "system_up_time": uptime}
            return JsonResponse(response, safe=False, status=200)



        except Exception as ex:
            print("Error on line {}".format(sys.exc_info()[-1].tb_lineno), type(ex).__name__, ex)
            error = {
                "message": "something went wrong"
            }
            return JsonResponse(error, safe=False, status=500)