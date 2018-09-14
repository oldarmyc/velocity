# Velocity

Asynchronous library for interacting with swift containers

#### Variables

##### Required

*USERNAME* - Username to authenticate with

*PW_OR_API_KEY* - Password or API key for user. For Rackspace this
                  will be API Key

*REGION* - Region to interact with

*CONTAINER* - Container to use  
**Note:** If running an upload the container will be created if not already present

*ACTION_TO_PERFORM* - Action to perform which can be one of the following:
  * HEAD : Check if the file(s) exists in the specified container
  * DELETE : Delete file(s) from the specified container
  * UPLOAD : Upload file(s) to the specified container
  * DOWNLOAD : Download file(s) to the specified file location

*FILE_LOCATION* - Absolute path of directory on system
  * Upload: Source location of the files to upload
  * Download: Location to download the file to

##### Optional

*AUTH_URL* - Auth URL to use when authenticating the user  
**Default:** Rackspace authentication URL https://identity.api.rackspacecloud.com/v2.0

*INTERNAL* - If there are internal links for swift use those  
**Default:** Use public URLs from the service catalog

*IDENTITY* - Identity option to specify how to derive the authentication data payload  
**Default:** Is Rackspace which utilizes the API Key instead of users password


#### Sample Usage

```python

from velocity import Velocity


import asyncio

# Initiate the loop and will be passed to the object
loop = asyncio.get_event_loop()
velocity = Velocity(loop, USERNAME, PW_OR_API_KEY, REGION)
try:
    velocity.authenticate()
    if action == 'upload':
        velocity.create_container(CONTAINER)

    # Start running the action
    loop.run_until_complete(
        velocity.process(CONTAINER, ACTION_TO_PERFORM, FILE_LOCATION)
    )
except Exception as e:
    print(f'There was an exception here {e}')
finally:
    # Make sure the session is closed even on exception
    loop.run_until_complete(velocity.close_session())

# Close the loop out
loop.close()

# Get any errors generated from the action
if len(velocity.errors) > 0:
    for error in velocity.errors:
        print(error)
else:
    print(f'Huzzah! No errors reported for action {action}')

```
