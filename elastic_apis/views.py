from rest_framework.views import APIView
from django.http import HttpResponse, JsonResponse
from elastic_search_api_new.settings import es_url
import os, sys
import psutil
import docker
from datetime import datetime, timedelta


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
            target_services = ['elasticsearch', 'dockerd', 'zeek', 'suricata', 'tshark', "filebeat"]
            containers_info = []

            # Get all running processes
            for process in psutil.process_iter(['pid', 'name', 'cpu_percent', 'status']):
                try:
                    # Check if it's one of the target services
                    if process.info['name'] in target_services:  # and process.info['status'] != psutil.STATUS_ZOMBIE:
                        # Increase the interval for more accurate CPU usage
                        cpu_percent = process.cpu_percent(interval=1)  # Set interval to 0.5 seconds
                        containers_info.append({
                            "pid": process.info['pid'],
                            'name': process.info['name'],
                            'status': process.info['status']
                        })
                except psutil.AccessDenied:
                    # Skip this process if access is denied
                    pass

            ## get the docker details
            client = docker.from_env()
            # System uptime
            uptime_seconds = datetime.now().timestamp() - psutil.boot_time()
            uptime = str(timedelta(seconds=int(uptime_seconds)))

            docker_processes = []

            # Iterate over all containers
            for container in client.containers.list(all=True):
                stats = container.stats(stream=False)
                print(stats)
                cpu_usage = stats['cpu_stats']['cpu_usage']['total_usage']
                system_cpu_usage = stats['precpu_stats']['cpu_usage']['total_usage']
                memory_usage = stats['memory_stats']['usage'] if "usage" in stats['memory_stats'] else 0
                network_interface_usage = stats['networks'] if "networks" in stats else 0
                status = container.status
                name = container.name
                ip_address = container.attrs['NetworkSettings']['IPAddress']

                containers_info.append({
                    'name': name,
                    'status': status,
                    'cpu_usage': cpu_usage,
                    'system_cpu_usage': system_cpu_usage,
                    'memory_usage': memory_usage,
                    'network_usage': network_interface_usage,
                    'ip_address': ip_address
                })

            response = {"data": containers_info, "message": "Data Found", "system_up_time": uptime}
            return JsonResponse(response, safe=False, status=200)



        except Exception as ex:
            print("Error on line {}".format(sys.exc_info()[-1].tb_lineno), type(ex).__name__, ex)
            error = {
                "message": "something went wrong"
            }
            return JsonResponse(error, safe=False, status=500)