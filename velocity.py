
from urllib.parse import quote


import requests
import aiofiles
import asyncio
import aiohttp
import json
import os


class Velocity(object):
    def __init__(self, loop, username, password, region, auth_url=None,
                 identity=None, internal=False):

        self.region = region
        self.username = username

        # If rackspace this is api_key and if keystone it is password
        self.password = password

        # Use internal URLs or public URLs from service catalog
        self.internal = False

        self.auth_url = auth_url
        if self.auth_url is None:
            self.auth_url = 'https://identity.api.rackspacecloud.com/v2.0'

        if identity is None:
            self.identity = 'rackspace'
        else:
            self.identity = identity.lower()

        # Defaults for now not sure if I want it to be configurable
        self.workers = 100
        self.limit = 10000
        self.queue_size = 30000
        self.retry_limit = 1
        self.session = aiohttp.ClientSession(loop=loop)

        # Set in consumer to capture any errors
        self.errors = []

        # Set during authentication
        self._endpoint = None
        self._token = None

        # Set at initial action setup
        self._container = None
        self._action = None
        self._queue = None
        self._lock = None

        # Set in producer if container has more items than specified limit
        self._marker = None

    def set_headers(self, content_type=True, add_token=True):
        """Header set function to use in all calls made"""
        headers = {}
        if content_type:
            headers['Content-Type'] = 'application/json'

        if add_token and self._token is not None:
            headers['X-Auth-Token'] = self._token

        return headers

    def authenticate(self, auth_only=False):
        authentication_url = f'{self.auth_url}/tokens'
        if self.identity == 'rackspace':
            authentication_payload = {
                'auth': {
                    'RAX-KSKEY:apiKeyCredentials': {
                        'username': self.username,
                        'apiKey': self.password
                    }
                }
            }
        elif self.identity == 'keystone':
            authentication_payload = {
                'auth': {
                    'passwordCredentials': {
                        'username': self.username,
                        'password': self.password
                    }
                }
            }
        else:
            raise SystemExit('Unsupported identity/OS_AUTH_SYSTEM provided')

        r = requests.post(
            authentication_url,
            data=json.dumps(authentication_payload),
            headers=self.set_headers(add_token=False)
        )
        r.raise_for_status()
        auth_return = r.json()
        try:
            self._token = auth_return['access']['token']['id']
            service_catalog = auth_return['access']['serviceCatalog']
        except Exception:
            raise SystemExit('Could not parse authentication response')

        # If needing a reauth no need to process the service catalog
        if auth_only is False:
            # Check for internal or external URL to use when talking to swift
            if self.internal:
                url_type = 'internalURL'
            else:
                url_type = 'publicURL'

            for service in service_catalog:
                if (
                    service['type'] == 'object-store' and
                    service['name'] in ['cloudFiles', 'swift']
                ):
                    for temp_endpoint in service['endpoints']:
                        if temp_endpoint.get('region') == self.region:
                            self._endpoint = temp_endpoint.get(url_type)
                            break
                    break

            if self._endpoint is None:
                raise SystemExit('Endpoint not found')

    def create_container(self, container):
        item_url = f'{self._endpoint}/{container}'
        print(f'Ensuring container {container} is present for upload')

        # Checking for container existence for upload
        r = requests.put(
            item_url,
            headers=self.set_headers(content_type=False, add_token=True)
        )
        r.raise_for_status()
        print(f'Container {container} check/create was successful')

    async def close_session(self):
        await self.session.close()

    async def upload_producer(self, file_path):
        for root, _, files in os.walk(file_path, topdown=True):
            print('Placing objects in queue')
            for file_name in files:
                await self._queue.put(
                    {
                        'full_path': quote(
                            os.path.join(root, file_name).encode('utf-8')
                        ),
                        'name': quote(
                            os.path.relpath(
                                os.path.join(root, file_name),
                                file_path
                            )
                        ),
                        'action': self._action
                    }
                )

        print('Completed adding objects to queue')

    async def producer(self):
        exit = False
        while exit is False:
            objects = []
            list_url = (
                f'{self._endpoint}/{self._container}?'
                f'format=json&limit={self.limit}'
            )
            if self._marker is not None:
                list_url = f'{list_url}&marker={self._marker}'

            async with self.session.get(
                list_url,
                headers=self.set_headers(add_token=True)
            ) as r:
                objects = await r.json()

            if len(objects) == self.limit:
                self._marker = objects[-1]['name']

                # Remove just for testing
                exit = True
            else:
                exit = True

            print('Placing objects in queue')
            for item in objects:
                queue_item = {
                    'name': quote(item.get('name').encode('utf-8')),
                    'action': self._action
                }
                if self._action == 'upload':
                    queue_item['retry_count'] = 0

                await self._queue.put(queue_item)

        print('Completed adding objects to queue')

    async def consumer(self, worker_number, file_path=None):
        while True:
            item = await self._queue.get()
            print(
                f"Consumer {worker_number}: Processing {item.get('name')}"
            )
            item_url = (
                f"{self._endpoint}/{self._container}/{item.get('name')}"
            )

            # Headers are the same for every type of request
            headers = self.set_headers(content_type=False, add_token=True)
            if item.get('action') == 'head':
                await self.process_head(headers, item_url, item)
            elif item.get('action') == 'delete':
                await self.process_delete(headers, item_url, item)
            elif item.get('action') == 'upload':
                await self.process_upload(headers, item_url, item)
            elif item.get('action') == 'download':
                await self.process_download(headers, item_url, item, file_path)

            # Notify the queue that the item has been processed
            self._queue.task_done()

    async def process_head(self, headers, item_url, item):
        async with self.session.head(
            item_url,
            headers=headers
        ) as r:
            if r.status != 200:
                self.errors.append(
                    f"Error checking for {item.get('name')}"
                    f" received {r.status} code on HEAD request"
                )
            else:
                print(f'Got status of {r.status}')

    async def process_delete(self, headers, item_url, item):
        zero_byte_fix = False

        async with self.session.delete(
            item_url,
            headers=headers
        ) as r:
            if r.status != 204:
                self.errors.append(
                    f"Failed to delete {item.get('name')}"
                    f" received {r.status} code on DELETE request"
                )

            # If 404 then do mark the file for zero byte fix
            if r.status == 404:
                zero_byte_fix = True

        # Check for zero byte fix and make sure retry count is not exceeded
        if (
            zero_byte_fix is True and
            item.get('retry_count') and
            item.get('retry_count') < self.retry_limit
        ):
            print('Trying zero byte fix')

            # Increment the retry count
            item['retry_count'] += 1

            async with self.session.put(
                item_url,
                headers=headers,
                data=''
            ) as r:
                # If upload succeeded put file back on queue
                if r.status == 201:
                    await self._queue.put(item)
                else:
                    self.errors.append(
                        f"Error using zero byte fix for {item.get('name')}"
                        f" received {r.status} code on PUT request"
                    )

    async def process_upload(self, headers, item_url, item):
        with open(item.get('full_path'), 'rb') as f:
            await self.session.put(item_url, headers=headers, data=f)

    async def process_download(self, headers, item_url, item, file_path):
        full_path = os.path.join(file_path, item.get('name'))

        try:
            os.makedirs(os.path.dirname(full_path), mode=0o755)
        except OSError as e:
            # Error 17 is already exists which is fine just overwrite
            if e.errno != 17:
                print(f'Error creating full path {e}')
                raise

        async with self.session.get(item_url, headers=headers) as r:
            if r.status == 200:
                async with aiofiles.open(full_path, 'wb+') as f:
                    await f.write(await r.read())
                    await f.flush()
            else:
                self.errors.append(
                    f"Error downloading {item.get('name')}"
                    f" received {r.status} code on GET request"
                )

    async def process(self, container, action, file_path=None):
        # Store container and action so as not to have to pass it around
        self._container = container
        self._action = action

        if self._action in ['download', 'upload']:
            if file_path is None:
                raise SystemExit(
                    'Must include path to download to or upload from'
                )

        if file_path is not None:
            if not os.path.isdir(file_path):
                raise SystemExit(
                    f'Path {file_path} for {action} is not a directory'
                )

        # Initialize queue and lock and set on class
        self._queue = asyncio.Queue()
        self._lock = asyncio.Lock()

        # Setup consumers based on the number of workers
        consumers = [
            asyncio.ensure_future(
                self.consumer(x, file_path)
            ) for x in range(self.workers)
        ]

        # Run the producer and wait for completion
        if self._action == 'upload':
            await self.upload_producer(file_path)
        else:
            await self.producer()

        # Wait until the consumer has processed all items
        await self._queue.join()

        # Consumers are still waiting so cancel each of them
        for consumer_future in consumers:
            consumer_future.cancel()

        # Close out the session on completion
        await self.session.close()
