class LightEngineError(Exception):
    pass


class GoveeApiError(LightEngineError):
    pass


class DeviceNotFoundError(LightEngineError):
    pass


class AmbiguousDeviceError(LightEngineError):
    pass


class UnsupportedCapabilityError(LightEngineError):
    pass
