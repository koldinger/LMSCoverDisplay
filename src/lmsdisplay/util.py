from datetime import datetime
from contextlib import suppress

def parsetime(timestr):
    with suppress(ValueError):
        return datetime.strptime(timestr, "%H:%M",).time()
    with suppress(ValueError):
        return datetime.strptime(timestr, "%I:%M%p").time()
    with suppress(ValueError):
        return datetime.strptime(timestr, "%H").time()
    with suppress(ValueError):
        return datetime.strptime(timestr, "%I%p").time()
    raise ValueError(f"Unable to parse time string: {timestr}")

def betweentimes(now, start, end):
    if start <= end:
        return start <= now <= end
    return now <= end or now >= start


if __name__ == "__main__":
    for i in ["11pm", "23", "11:30pm", "11:30", "23:30", "24:30", "13pm"]:
        try:
            print(i, parsetime(i))
        except ValueError as e:
            print(e)

    print(betweentimes(parsetime("11"), parsetime("1"), parsetime("13")))
    print(betweentimes(parsetime("11"), parsetime("13"), parsetime("1")))
    print(betweentimes(parsetime("11"), parsetime("10"), parsetime("1")))
