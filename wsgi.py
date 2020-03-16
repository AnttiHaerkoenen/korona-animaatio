import datetime

import dash
import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Output, Input
import pandas as pd
import plotly.express as px
import requests


headers = {
    'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/53.0.2785.143 Safari/537.36',
}

data_url = 'https://w3qa5ydb4l.execute-api.eu-west-1.amazonaws.com/prod/finnishCoronaData'

FIRST = '2020-01-28'

LOCATIONS = {
    'shp': [
        'Itä-Savo',
        'HUS',
        'Pirkanmaa',
        'Etelä-Karjala',
        'Kymenlaakso',
        'Päijät-Häme',
        'Pohjois-Savo',
        'Etelä-Savo',
        'Keski-Suomi',
        'Pohjois-Karjala',
        'Pohjois-Pohjanmaa',
        'Kainuu',
        'Keski-Pohjanmaa',
        'Lappi',
        'Länsi-Pohja',
        'Etelä-Pohjanmaa',
        'Kanta-Häme',
        'Varsinais-Suomi',
        'Satakunta',
        'Vaasa',
    ],
    'lat': [
        61.868351,
        60.169857,
        61.499003,
        61.058449,
        60.8366623,
        60.982104,
        62.9967201,
        61.688925,
        62.1332752,
        62.6478798,
        65.2032821,
        64.2151151,
        63.8438269,
        66.6659629,
        65.8803706,
        62.7985647,
        60.9947862,
        60.7553591,
        61.4799843,
        63.0689039,
    ],
    'lon': [
        28.886259,
        24.938379,
        23.759720,
        28.186991,
        26.5435711,
        25.6317823,
        27.1134536,
        27.2441327,
        25.9983345,
        29.7932692,
        25.8824512,
        27.6334433,
        23.0999967,
        24.9109831,
        25.0380235,
        22.7538696,
        24.3781338,
        22.2292106,
        21.7589953,
        22.0,
    ],
}
LOCATION_MAPPER = {k: (x, y) for k, x, y in zip(LOCATIONS['shp'], LOCATIONS['lat'], LOCATIONS['lon'])}


def make_dataframe(json_list):
    cases = [
        (
            case['date'].split('T')[0],
            case['healthCareDistrict'],
            1,
        )
        for case
        in json_list
    ]
    data = pd.DataFrame.from_records(cases, columns=['pvm', 'shp', 'n'])

    if data.empty:
        return data

    sums = data.groupby(['pvm', 'shp'], as_index=False)['n'].sum()

    sums = sums.sort_values(by=['shp', 'pvm'])

    parts = [
        sums[sums.shp == p]
        for p
        in sums.shp.unique()
    ]

    districts = []
    today = str(datetime.date.today())

    for p in parts:
        d = p
        d.loc[:, 'n'] = p.n.cumsum()

        if today in d.pvm.values:
            first_last = pd.DataFrame.from_dict({
                'pvm': [FIRST],
                'shp': [d.shp.values[0]],
                'n': [0]
            })
        else:
            first_last = pd.DataFrame.from_dict({
                'pvm': [FIRST, today],
                'shp': [d.shp.values[0]] * 2,
                'n': [0, d.iat[-1, 2]]
            })

        d = d.append(first_last)

        d.loc[:, 'pvm'] = pd.to_datetime(d['pvm'])
        d = d.set_index('pvm')
        d = d.resample('1D').ffill()
        districts.append(d)

    sums = pd.concat(districts)
    sums = sums.reset_index().set_index(['pvm', 'shp'])

    return sums


req = requests.get(
        data_url,
        headers=headers,
        timeout=60,
)

result = req.json()

confirmed = make_dataframe(result['confirmed']).rename(columns={'n': 'confirmed'})
deaths = make_dataframe(result['deaths']).rename(columns={'n': 'deaths'})
recovered = make_dataframe(result['recovered']).rename(columns={'n': 'recovered'})

total = pd.concat([confirmed, deaths, recovered], axis=1).drop(columns=['pvm', 'shp']).fillna(0)
total['active'] = total['confirmed'] - total['deaths'] - total['recovered']

total.reset_index(inplace=True)
total['pvm'] = total['pvm'].apply(lambda d: str(d).split()[0])
total['lat'] = total.shp.apply(lambda p: LOCATION_MAPPER.get(p, (None, None))[0])
total['lon'] = total.shp.apply(lambda p: LOCATION_MAPPER.get(p, (None, None))[1])
total = total[total['pvm'] > '2020-03']

app = dash.Dash(__name__)
app.title = "Korona-animaatio"

fig = px.scatter_mapbox(
    total,
    lat="lat",
    lon="lon",
    color="shp",
    hover_name="shp",
    hover_data="confirmed deaths recovered".split(),
    size="active",
    # projection="mercator",
    # scope="europe",
    animation_frame="pvm",
    center={'lat': 63.4, 'lon': 26.0},
    zoom=4,
    size_max=25,
    height=600,
    width=None,
)
fig.update_layout(mapbox_style="carto-darkmatter")

application = app.server

app.layout = html.Div(children=[
    html.H2(children='Suomen koronavirustartunnat'),
    html.H4(children='Tapaukset sairaanhoitopiireittäin 2020-03-01 alkaen'),

    dcc.Graph(
        id='map',
        figure=fig,
    ),

    html.P(children='Antti Härkönen 2020')
])


if __name__ == '__main__':
    app.run_server(
        port=8080,
        host='0.0.0.0',
        debug=True,
    )
