"""Download and map Dhan's instrument master for PSY29."""

from io import StringIO
import pandas as pd
import requests

URL = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"


def download_master():
    r = requests.get(URL, timeout=60)
    r.raise_for_status()
    return pd.read_csv(StringIO(r.text), low_memory=False)


def nse_equities():
    df = download_master()
    return df[(df["EXCH_ID"] == "NSE") & (df["SEGMENT"] == "E")].copy()
