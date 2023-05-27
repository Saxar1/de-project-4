import requests
import pandas as pd
import json
from datetime import datetime, timedelta


url = "https://d5d04q7d963eapoepsqr.apigw.yandexcloud.net/deliveries"
headers = headers = {
                        "X-Nickname": "saxarok",
                        "X-Cohort": "11",
                        "X-API-KEY": "25c27781-8fde-4b30-a22e-524044a7580f"
                    }
limit = 50
sort_field = 'date'
sort_direction = 'asc'
end_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
start_date = (datetime.strptime(end_date, '%Y-%m-%d %H:%M:%S').replace(hour=0, minute=0, second=0) - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
offset = 0

data_list = []
while True:
    params = {
        'limit': limit,
        'offset': offset,
        'sort_field': sort_field,
        'sort_direction': sort_direction,
        'start_date': start_date,
        'end_date': end_date
    }
    response = requests.get(url, params=params, headers=headers)
    if response.status_code == 200:
        data = json.loads(response.text)
        
        if not data:
            break
        data_list.extend(data) 
        offset += limit
    else:
        raise ValueError(f'Request failed with status code {response.status_code}')

print(data_list)

# for row in df_out.itertuples(index=False):
#     print(row)


# df_out.to_csv('data.csv')
# print(df_out.head(5))
# print(df_out.info())
    

