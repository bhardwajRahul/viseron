import logging
import os
import re

from voluptuous import All, Any, Length, Optional, Range, Required, Schema, Invalid

import numpy as np
from const import (
    CAMERA_GLOBAL_ARGS,
    CAMERA_HWACCEL_ARGS,
    CAMERA_INPUT_ARGS,
    CAMERA_OUTPUT_ARGS,
    DECODER_CODEC,
    ENV_CUDA_SUPPORTED,
    ENV_RASPBERRYPI3,
    ENV_VAAPI_SUPPORTED,
    HWACCEL_CUDA_DECODER_CODEC,
    HWACCEL_RPI3_DECODER_CODEC,
    HWACCEL_VAAPI,
)
from lib.helpers import slugify

from .config_logging import SCHEMA as LOGGING_SCHEMA
from .config_object_detection import LABELS_SCHEMA

LOGGER = logging.getLogger(__name__)

MQTT_NAME_REGEX = re.compile(r"^[a-zA-Z0-9_\.]+$")


def ensure_mqtt_name(camera: dict) -> dict:
    if camera["mqtt_name"] is None:
        camera["mqtt_name"] = slugify(camera["name"])

    match = MQTT_NAME_REGEX.match(camera["mqtt_name"])

    if not match:
        raise Invalid(
            f"Error in config for camera {camera['name']}. "
            f"mqtt_name can only contain the characters [a-zA-Z0-9_], "
            f"got {camera['mqtt_name']}"
        )

    return camera


def check_for_hwaccels(hwaccel_args: list) -> list:
    if hwaccel_args:
        return hwaccel_args

    if os.getenv(ENV_VAAPI_SUPPORTED) == "true":
        return HWACCEL_VAAPI
    return hwaccel_args


def get_codec(camera: dict) -> dict:
    if camera["codec"]:
        return camera

    if camera["stream_format"] == "rtsp":
        if os.getenv(ENV_CUDA_SUPPORTED) == "true":
            camera["codec"] = HWACCEL_CUDA_DECODER_CODEC
        elif os.getenv(ENV_RASPBERRYPI3) == "true":
            camera["codec"] = HWACCEL_RPI3_DECODER_CODEC
        else:
            camera["codec"] = DECODER_CODEC
    return camera


SCHEMA = Schema(
    All(
        [
            All(
                {
                    Required("name"): All(str, Length(min=1)),
                    Optional("mqtt_name", default=None): Any(
                        All(str, Length(min=1)), None
                    ),
                    Required("stream_format", default="rtsp"): Any("rtsp", "mjpeg"),
                    Required("host"): All(str, Length(min=1)),
                    Required("port"): All(int, Range(min=1)),
                    Optional("username", default=None): Any(
                        All(str, Length(min=1)), None
                    ),
                    Optional("password", default=None): Any(
                        All(str, Length(min=1)), None
                    ),
                    Required("path"): All(str, Length(min=1)),
                    Optional("width", default=None): Any(int, None),
                    Optional("height", default=None): Any(int, None),
                    Optional("fps", default=None): Any(All(int, Range(min=1)), None),
                    Optional("global_args", default=CAMERA_GLOBAL_ARGS): list,
                    Optional("input_args", default=CAMERA_INPUT_ARGS): list,
                    Optional(
                        "hwaccel_args", default=CAMERA_HWACCEL_ARGS
                    ): check_for_hwaccels,
                    Optional("codec", default=""): str,
                    Optional("rtsp_transport", default="tcp"): Any(
                        "tcp", "udp", "udp_multicast", "http"
                    ),
                    Optional("filter_args", default=[]): list,
                    Optional("motion_detection", default=None): Any(
                        {
                            Optional("interval"): Any(int, float),
                            Optional("trigger_detector"): bool,
                            Optional("timeout"): bool,
                            Optional("max_timeout"): int,
                            Optional("width"): int,
                            Optional("height"): int,
                            Optional("area"): float,
                            Optional("frames"): int,
                            Optional("mask", default=[]): [
                                {
                                    Required("points"): [
                                        {Required("x"): int, Required("y"): int,}
                                    ],
                                }
                            ],
                            Optional("logging", default={}): LOGGING_SCHEMA,
                        },
                        None,
                    ),
                    Optional("object_detection", default=None): Any(
                        {
                            Optional("interval"): Any(int, float),
                            Optional("labels"): LABELS_SCHEMA,
                        },
                        None,
                    ),
                    Optional("zones", default=[]): [
                        {
                            Required("name"): str,
                            Required("points"): [
                                {Required("x"): int, Required("y"): int,}
                            ],
                            Optional("labels"): LABELS_SCHEMA,
                        }
                    ],
                    Optional("publish_image", default=False): Any(True, False),
                    Optional("logging", default={}): LOGGING_SCHEMA,
                },
                get_codec,
                ensure_mqtt_name,
            )
        ],
    )
)


class CameraConfig:
    schema = SCHEMA

    def __init__(self, camera):
        self._name = camera.name
        self._name_slug = slugify(self.name)
        self._mqtt_name = camera.mqtt_name
        self._stream_format = camera.stream_format
        self._host = camera.host
        self._port = camera.port
        self._username = camera.username
        self._password = camera.password
        self._path = camera.path
        self._width = camera.width
        self._height = camera.height
        self._fps = camera.fps
        self._global_args = camera.global_args
        self._input_args = camera.input_args
        self._hwaccel_args = camera.hwaccel_args
        self._codec = camera.codec
        self._rtsp_transport = camera.rtsp_transport
        self._filter_args = camera.filter_args
        self._motion_detection = camera.motion_detection
        self._object_detection = camera.object_detection
        self._zones = self.generate_zones(camera.zones)
        self._publish_image = camera.publish_image
        self._logging = camera.logging

    def generate_zones(self, zones):
        zone_list = []
        for zone in zones:
            zone_dict = {}
            zone_dict["name"] = zone.name

            zone_labels = getattr(zone, "labels", [])
            if not zone_labels:
                zone_labels = getattr(self.object_detection, "labels", [])
            zone_dict["labels"] = zone_labels

            point_list = []
            for point in getattr(zone, "points"):
                point_list.append([getattr(point, "x"), getattr(point, "y")])
            zone_dict["coordinates"] = np.array(point_list)
            zone_list.append(zone_dict)

        return zone_list

    @property
    def name(self):
        return self._name

    @property
    def name_slug(self):
        return self._name_slug

    @property
    def mqtt_name(self):
        return self._mqtt_name

    @property
    def stream_format(self):
        return self._stream_format

    @property
    def host(self):
        return self._host

    @property
    def port(self):
        return self._port

    @property
    def username(self):
        return self._username

    @property
    def password(self):
        return self._password

    @property
    def path(self):
        return self._path

    @property
    def width(self):
        return self._width

    @property
    def height(self):
        return self._height

    @property
    def fps(self):
        return self._fps

    @property
    def protocol(self):
        return "rtsp" if self.stream_format == "rtsp" else "http"

    @property
    def stream_url(self):
        if self.username and self.password:
            return (
                f"{self.protocol}://{self.username}:{self.password}@"
                f"{self.host}:{self.port}{self.path}"
            )
        return f"{self.protocol}://{self.host}:{self.port}{self.path}"

    @property
    def global_args(self):
        return self._global_args

    @property
    def input_args(self):
        return self._input_args

    @property
    def hwaccel_args(self):
        return self._hwaccel_args

    @property
    def codec(self):
        return ["-c:v", self._codec] if self._codec else []

    @property
    def rtsp_transport(self):
        return self._rtsp_transport

    @property
    def filter_args(self):
        return self._filter_args

    @property
    def output_args(self):
        return CAMERA_OUTPUT_ARGS

    @property
    def motion_detection(self):
        return self._motion_detection

    @property
    def object_detection(self):
        return self._object_detection

    @property
    def zones(self):
        return self._zones

    @property
    def publish_image(self):
        return self._publish_image

    @property
    def logging(self):
        return self._logging
