#!/usr/bin/env python
from datetime import datetime
from enum import Enum
import time
import traceback
import json
import boto3
import botocore
import sys
import os
import keybow
import time

import awsiot.greengrasscoreipc
import awsiot.greengrasscoreipc.client as client
from awsiot.greengrasscoreipc.model import (
    IoTCoreMessage,
    QOS,
    SubscribeToIoTCoreRequest,
    PublishToIoTCoreRequest
)

class State(str, Enum):
    AVAILABLE = 'available'
    BUSY = 'busy'
    TENTATIVE = 'tentative'
    UNKNOWN = 'unknown'

# Setup some constants and pull command line args and environment variables.
TIMEOUT = 10
BUCKET = sys.argv[1]
REQUEST_TOPIC = sys.argv[2]
RESPONSE_TOPIC = sys.argv[3]
THING_NAME = os.getenv('AWS_IOT_THING_NAME', 'unknown')

current_state = State.AVAILABLE
requested_state = ''
ipc_client = awsiot.greengrasscoreipc.connect()

keybow.setup(keybow.MINI)


@keybow.on()
def handle_key(index, state):
    print("{}: Key {} has been {}".format(
        time.time(),
        index,
        'pressed' if state else 'released'))

    if index == 0:
        requested_state = State.AVAILABLE
    elif index == 1:
        requested_state = State.BUSY
    elif index == 2:
        requested_state = State.TENTATIVE
    else:
        requested_state = State.UNKNOWN

    #make a request only if recognized cmd
    if (requested_state != State.UNKNOWN):
        change_state("button " + index, requested_state)
        respond(None)

def change_state(changeSource, requestedState):
    try:
        if requestedState == State.BUSY:
            keybow.set_led(0, 255, 0, 0)
            keybow.set_led(1, 255, 0, 0)
            keybow.set_led(2, 255, 0, 0)
            current_state = State.BUSY
        elif requestedState == State.AVAILABLE:
            keybow.set_led(0, 0, 255, 0)
            keybow.set_led(1, 0, 255, 0)
            keybow.set_led(2, 0, 255, 0)
            current_state = State.AVAILABLE
        elif requestedState == State.TENTATIVE:
            keybow.set_led(0, 0, 0, 255)
            keybow.set_led(1, 0, 0, 255)
            keybow.set_led(2, 0, 0, 255)
            current_state = State.TENTATIVE
        else:
            print("unrecognized request: " + requestedState)
            return False

        return True
    except: 
        traceback.print_exc()
        return False
    finally:
        #reset the temp request state
        requested_state = ''

def respond(event):
    # This is the main response function when we notice a message on the request topic.
    # result = take_picture()
    # if picture_result == "failed":
    #     image_url = "Unable to get picture"
    # elif picture_result == "success":
    #     image_url = upload_file(BUCKET, TEMP_PIC)

    response_message = {
        "timestamp": int(round(time.time() * 1000)),
        "state": current_state
    }

    # Using the AWS IOT SDK to publish messages directly to AWS.  Using QOS=1 (AT_LEAST_ONCE) to have Greengrass queue up
    # the messages if we happen to loose internet connectivity...which happens with the LTE modem
    response = PublishToIoTCoreRequest()
    response.topic_name = RESPONSE_TOPIC
    response.payload = bytes(json.dumps(response_message), "utf-8")
    response.qos = QOS.AT_LEAST_ONCE
    response_op = ipc_client.new_publish_to_iot_core()
    response_op.activate(response)

class StreamHandler(client.SubscribeToIoTCoreStreamHandler):
    # Setup a class to do stuff upon topic activity.
    def __init__(self):
        super().__init__()

    def on_stream_event(self, event: IoTCoreMessage) -> None:
        try:
            respond(event)
        except:
            traceback.print_exc()

    def on_stream_error(self, error: Exception) -> bool:
        # Handle error.
        return True  # Return True to close stream, False to keep stream open.

    def on_stream_closed(self) -> None:
        # Handle close.
        pass


# Setup the MQTT Subscription
request = SubscribeToIoTCoreRequest()
request.topic_name = REQUEST_TOPIC
request.qos = QOS.AT_LEAST_ONCE
handler = StreamHandler()
operation = ipc_client.new_subscribe_to_iot_core(handler)
future = operation.activate(request)
future.result(TIMEOUT)

while True:
    keybow.show()
    time.sleep(1.0 / 60.0)

# To stop subscribing, close the operation stream.
operation.close()