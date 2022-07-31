import datetime

import pytz
import tzlocal


def localize_timezone(dt: datetime.datetime) -> datetime.datetime:
    return pytz.timezone(tzlocal.get_localzone_name()).localize(dt)
