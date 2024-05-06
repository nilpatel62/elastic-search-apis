import datetime

from rest_framework.views import APIView
from django.http import HttpResponse, JsonResponse
from elastic_search_api_new.settings import es_url
import os, sys
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated  # <-- Here

# Define the index name
user_index_name = "users"
role_index_name = "roles"


# Create your views here.
class AccessRoles(APIView):
    permission_classes = (IsAuthenticated,)
    def post(self, request):
        try:
            data = request.data
            name = data.get("name")
            access = data.get("access")
            if not name:
                return JsonResponse({'error': 'name is required in the JSON body.'}, status=400)
            if not isinstance(name, str):
                return JsonResponse({'error': 'Filenames must be an string.'}, status=400)
            if not access:
                return JsonResponse({'error': 'access is required in the JSON body.'}, status=400)
            if not isinstance(access, dict):
                return JsonResponse({'error': 'Filenames must be a object.'}, status=400)

            must_query = [{"match_phrase_prefix": {"role_name": name}}]
            ## first need to check if we have already added role in database with the same name
            search_query = {
                "query": {
                    "bool": {
                        "must": must_query,
                        "minimum_should_match": 1,
                        "boost": 1.0,
                    }
                },
                "size": 0,
                "from": 1 * 10,
            }

            res_filter_parameters = es_url.search(
                index=role_index_name,
                body=search_query,
                filter_path=[
                    "hits.hits._id",
                    "hits.hits._source.role_name",
                ],
            )
            if len(res_filter_parameters) == 0:
                json_data = {
                    "role_name": name,
                    "access": access,
                    "timestamp": int(datetime.datetime.now().timestamp())
                }
                es_url.index(index=role_index_name, body=json_data, op_type="create")

                response = {
                    "message": "Successfully Added the role"
                }
                return JsonResponse(response, safe=False, status=201)
            else:
                response = {
                    "message": "Role already added with same name"
                }
                return JsonResponse(response, safe=False, status=409)

        except Exception as ex:
            print("Error on line {}".format(sys.exc_info()[-1].tb_lineno), type(ex).__name__, ex)
            error = {
                "message": "something went wrong"
            }
            return JsonResponse(error, safe=False, status=500)

    def get(self, request):
        try:
            size = int(request.GET.get("size", 10))
            page = int(request.GET.get("page", 0))
            search = request.GET.get("search", "")
            must_query = []
            if search != "":
                must_query.append({"match_phrase_prefix": {"role_name": search}})

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
                index=role_index_name,
                body=search_query,
                filter_path=[
                    "hits.hits._id",
                    "hits.hits._source",
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
                            "role_name": _res['_source']['role_name'],
                            "access": _res['_source']['access'],
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


    def patch(self, request):
        try:
            data = request.data
            elastic_id = data.get("id")
            name = data.get("name")
            access = data.get("access")
            if not elastic_id:
                return JsonResponse({'error': 'id is required in the JSON body.'}, status=400)
            if not name:
                return JsonResponse({'error': 'name is required in the JSON body.'}, status=400)
            if not isinstance(name, str):
                return JsonResponse({'error': 'Filenames must be an string.'}, status=400)
            if not isinstance(elastic_id, str):
                return JsonResponse({'error': 'id must be an string.'}, status=400)
            if not access:
                return JsonResponse({'error': 'access is required in the JSON body.'}, status=400)
            if not isinstance(access, dict):
                return JsonResponse({'error': 'Filenames must be a object.'}, status=400)

            must_query = [{"match": {"_id": elastic_id}}]
            ## first need to check if we have already added role in database with the same name
            search_query = {
                "query": {
                    "bool": {
                        "must": must_query,
                        "minimum_should_match": 1,
                        "boost": 1.0,
                    }
                },
                "size": 0,
                "from": 1 * 10,
            }

            res_filter_parameters = es_url.search(
                index=role_index_name,
                body=search_query,
                filter_path=[
                    "hits.hits._id",
                    "hits.hits._source.role_name",
                ],
            )
            if len(res_filter_parameters) == 0:
                response = {
                    "message": "Role not found"
                }
                return JsonResponse(response, safe=False, status=404)
            else:
                es_url.update(
                    index=role_index_name,
                    id=str(elastic_id),
                    body={
                        "doc": {
                            "role_name": name,
                            "access": access
                        }
                    },
                )
                response = {
                    "message": "Role updated successfully"
                }
                return JsonResponse(response, safe=False, status=200)

        except Exception as ex:
            print("Error on line {}".format(sys.exc_info()[-1].tb_lineno), type(ex).__name__, ex)
            error = {
                "message": "something went wrong"
            }
            return JsonResponse(error, safe=False, status=500)



class UsersData(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        try:
            data = request.data
            name = data.get("name")
            email = data.get("email")
            password = data.get("password")
            role_id = data.get("role")
            status = data.get("status")
            permission = data.get("permission")
            if not name:
                return JsonResponse({'error': 'name is required in the JSON body.'}, status=400)
            if not isinstance(name, str):
                return JsonResponse({'error': 'Filenames must be an string.'}, status=400)
            if not email:
                return JsonResponse({'error': 'email is required in the JSON body.'}, status=400)
            if not isinstance(email, str):
                return JsonResponse({'error': 'email must be an string.'}, status=400)
            if not password:
                return JsonResponse({'error': 'password is required in the JSON body.'}, status=400)
            if not isinstance(password, str):
                return JsonResponse({'error': 'password must be an string.'}, status=400)
            if not role_id:
                return JsonResponse({'error': 'role is required in the JSON body.'}, status=400)
            if not isinstance(role_id, str):
                return JsonResponse({'error': 'role must be a string.'}, status=400)
            if not permission:
                return JsonResponse({'error': 'permission is required in the JSON body.'}, status=400)
            if not isinstance(permission, str):
                return JsonResponse({'error': 'permission must be a string.'}, status=400)
            if not status:
                return JsonResponse({'error': 'status is required in the JSON body.'}, status=400)
            if not isinstance(status, int):
                return JsonResponse({'error': 'status must be a string.'}, status=400)

            must_query = []
            must_query.append({"match": {"email": email}})
            ## first need to check if we have already added role in database with the same name
            search_query = {
                "query": {
                    "bool": {
                        "must": must_query
                    }
                },
                "size": 1,
                "from": 1,
            }

            try:
                res_filter_parameters = es_url.search(
                    index=user_index_name,
                    body=search_query,
                    filter_path=[
                        "hits.hits._id",
                        "hits.hits._source.name",
                    ],
                )
            except:
                res_filter_parameters = []
            print(res_filter_parameters)
            if len(res_filter_parameters) == 0:
                user = User.objects.create_user(name, email, password)
                user.save()
                json_data = {
                    "name": name,
                    "email":  email,
                    "password":  password,
                    "role": role_id,
                    "status": status,
                    "permission": permission,
                    "timestamp": int(datetime.datetime.now().timestamp())
                }
                es_url.index(index=user_index_name, body=json_data, op_type="create")
                response = {
                    "message": "Successfully Added the User"
                }
                return JsonResponse(response, safe=False, status=201)
            else:
                response = {
                    "message": "User already added with same email"
                }
                return JsonResponse(response, safe=False, status=409)

        except Exception as ex:
            print("Error on line {}".format(sys.exc_info()[-1].tb_lineno), type(ex).__name__, ex)
            error = {
                "message": "something went wrong"
            }
            return JsonResponse(error, safe=False, status=500)

    def get(self, request):
        try:
            size = int(request.GET.get("size", 10))
            page = int(request.GET.get("page", 0))
            search = request.GET.get("search", "")
            must_query = []
            if search != "":
                must_query.append({"match_phrase_prefix": {"name": search}})

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
                index=user_index_name,
                body=search_query,
                filter_path=[
                    "hits.hits._id",
                    "hits.hits._source",
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
                            "name": _res['_source']['name'],
                            "email": _res['_source']['email'],
                            "role": _res['_source']['role'],
                            "status": _res['_source']['status'],
                            "permission": _res['_source']['permission'],
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


    def patch(self, request):
        try:
            data = request.data
            elastic_id = data.get("id")
            name = data.get("name")
            email = data.get("email")
            role_id = data.get("role")
            permission = data.get("permission")
            if not elastic_id:
                return JsonResponse({'error': 'id is required in the JSON body.'}, status=400)
            if not name:
                return JsonResponse({'error': 'name is required in the JSON body.'}, status=400)
            if not isinstance(name, str):
                return JsonResponse({'error': 'Filenames must be an string.'}, status=400)
            if not email:
                return JsonResponse({'error': 'email is required in the JSON body.'}, status=400)
            if not isinstance(email, str):
                return JsonResponse({'error': 'email must be an string.'}, status=400)
            if not role_id:
                return JsonResponse({'error': 'role is required in the JSON body.'}, status=400)
            if not isinstance(role_id, str):
                return JsonResponse({'error': 'role must be a string.'}, status=400)
            if not permission:
                return JsonResponse({'error': 'permission is required in the JSON body.'}, status=400)
            if not isinstance(permission, str):
                return JsonResponse({'error': 'permission must be a string.'}, status=400)

            must_query = [{"match": {"_id": elastic_id}}]
            ## first need to check if we have already added role in database with the same name
            search_query = {
                "query": {
                    "bool": {
                        "must": must_query,
                        "minimum_should_match": 1,
                        "boost": 1.0,
                    }
                },
                "size": 0,
                "from": 1 * 10,
            }

            res_filter_parameters = es_url.search(
                index=user_index_name,
                body=search_query,
                filter_path=[
                    "hits.hits._id",
                    "hits.hits._source",
                ],
            )
            if len(res_filter_parameters) == 0:
                response = {
                    "message": "Role not found"
                }
                return JsonResponse(response, safe=False, status=404)
            else:
                es_url.update(
                    index=role_index_name,
                    id=str(elastic_id),
                    body={
                        "doc": {
                            "name": name,
                            "email": email,
                            "role": role_id,
                            "permission": permission,
                        }
                    },
                )
                response = {
                    "message": "Role updated successfully"
                }
                return JsonResponse(response, safe=False, status=200)

        except Exception as ex:
            print("Error on line {}".format(sys.exc_info()[-1].tb_lineno), type(ex).__name__, ex)
            error = {
                "message": "something went wrong"
            }
            return JsonResponse(error, safe=False, status=500)


class UserAuthenticate(APIView):
    def post(self, request, *args, **kwargs):
        try:
            username = User.objects.get(email=(request.data['email']).lower()).username
            user = authenticate(username=username, password=request.data['password'])
            if user:
                token, created = Token.objects.get_or_create(user=user)
                return Response({
                    'token': token.key,
                    'user_id': user.pk,
                    'email': user.email
                })
            else:
                return Response({'error': 'Invalid credentials'}, status=401)
        except Exception as ex:
            print("Error on line {}".format(sys.exc_info()[-1].tb_lineno), type(ex).__name__, ex)
            error = {
                "message": "something went wrong"
            }
            return JsonResponse(error, safe=False, status=500)
