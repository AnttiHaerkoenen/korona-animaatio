import datetime
from dateutil import tz

import dash
import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Input, Output
import pandas as pd
import plotly.express as px
import requests


class APIError(Exception):
    pass


HEADERS = {
    'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/53.0.2785.143 Safari/537.36',
}

DATA_URL = 'https://w3qa5ydb4l.execute-api.eu-west-1.amazonaws.com/prod/finnishCoronaData'

FIRST = '2020-01-28'

OPACITY = 0.8

LOCATION_MAPPER = {
    'Itä-Savo': (61.868351, 28.886259),
    'HUS': (60.169857, 24.938379),
    'Pirkanmaa': (61.499003, 23.75972),
    'Etelä-Karjala': (61.058449, 28.186991),
    'Kymenlaakso': (60.4776188, 26.9122204),
    'Päijät-Häme': (60.982104, 25.6317823),
    'Pohjois-Savo': (62.9967201, 27.1134536),
    'Etelä-Savo': (61.688925, 27.2441327),
    'Keski-Suomi': (62.1332752, 25.9983345),
    'Pohjois-Karjala': (62.6478798, 29.7932692),
    'Pohjois-Pohjanmaa': (65.0097291, 25.5145513),
    'Kainuu': (64.2151151, 27.6334433),
    'Keski-Pohjanmaa': (63.8438269, 23.0999967),
    'Lappi': (66.6659629, 24.9109831),
    'Länsi-Pohja': (65.7556343, 24.52454),
    'Etelä-Pohjanmaa': (62.7985647, 22.7538696),
    'Kanta-Häme': (60.9947862, 24.3781338),
    'Varsinais-Suomi': (60.431959, 22.0841279),
    'Satakunta': (61.4799843, 21.7589953),
    'Vaasa': (63.085024, 21.6148133)
}


def serve_layout():
    return html.Div(children=[
        html.H2(children='Suomen koronavirustartunnat', style={'text-align': 'center'}),
        html.H4(children='Aktiiviset tapaukset sairaanhoitopiireittäin 2020-03-01 alkaen', style={'text-align': 'center'}),

        dcc.RadioItems(
            id='switch',
            options=[
                {'label': 'Kaikki aktiiviset', 'value': 'total'},
                {'label': 'Uudet tartunnat', 'value': 'confirmed'},
            ],
            value='total',
        ),

        dcc.Graph(id='map'),

        dcc.Graph(id='bar-plot'),

        html.P(children='Antti Härkönen 2020'),
        html.P(id='source'),
    ])


app = dash.Dash(__name__)
app.title = "Korona-animaatio"

app.layout = serve_layout()

application = app.server


def make_data_frame(
        json_list,
        start_date: str,
        end_date: str,
        cumulative: bool,
):
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

    for p in parts:
        d = p

        if cumulative:
            d.loc[:, 'n'] = p.n.cumsum()

        if end_date not in d.pvm.values:
            if cumulative:
                d = d.append(pd.DataFrame.from_dict({
                    'pvm': [end_date],
                    'shp': [d.shp.values[0]],
                    'n': [d.iat[-1, 2]]
                }))
            else:
                d = d.append(pd.DataFrame.from_dict({
                    'pvm': [end_date],
                    'shp': [d.shp.values[0]],
                    'n': [0]
                }))

        if start_date not in d.pvm.values:
            d = d.append(pd.DataFrame.from_dict({
                'pvm': [FIRST],
                'shp': [d.shp.values[0]],
                'n': [0]
            }))

        d.loc[:, 'pvm'] = pd.to_datetime(d['pvm'])
        d = d.set_index('pvm')

        if cumulative:
            d = d.resample('1D').ffill()
        else:
            d = d.resample('1D').asfreq()
            d['shp'] = d['shp'].ffill()

        d = d[start_date:end_date]
        districts.append(d)

    sums = pd.concat(districts)
    sums = sums.reset_index().set_index(['pvm', 'shp'])

    return sums


def get_data(
        start_date: str,
        end_date: str,
        cumulative: bool,
):
    req = requests.get(
        DATA_URL,
        headers=HEADERS,
        timeout=60,
    )

    req.raise_for_status()
    result = req.json()

    if 'message' in result:
        raise APIError(result['message'])

    confirmed = make_data_frame(
        result['confirmed'],
        start_date=start_date,
        end_date=end_date,
        cumulative=cumulative,
    ).rename(columns={'n': 'confirmed'})

    deaths = make_data_frame(
        result['deaths'],
        start_date=start_date,
        end_date=end_date,
        cumulative=cumulative,
    ).rename(columns={'n': 'deaths'})

    recovered = make_data_frame(
        result['recovered'],
        start_date=start_date,
        end_date=end_date,
        cumulative=cumulative,
    ).rename(columns={'n': 'recovered'})

    total = pd.concat([confirmed, deaths, recovered], axis=1).drop(columns=['pvm', 'shp']).fillna(0)
    total['active'] = total['confirmed'] - total['deaths'] - total['recovered']

    total.reset_index(inplace=True)

    total['pvm'] = total['pvm'].apply(lambda d: str(d).split()[0])
    total['lat'] = total.shp.apply(lambda p: LOCATION_MAPPER.get(p, (None, None))[0])
    total['lon'] = total.shp.apply(lambda p: LOCATION_MAPPER.get(p, (None, None))[1])

    return total


@app.callback(
    [Output('map', 'figure'),
     Output('bar-plot', 'figure'),
     Output('source', 'children')],
    [Input('switch', 'value')],
    )
def update_figures(option):
    today = datetime.datetime.now(tz=tz.gettz('Helsinki'))
    date_ = today.date().isoformat()
    hour_ = today.time().hour
    minute_ = today.time().minute

    update_time = f"Aineisto on peräisin Helsingin Sanomien avoimesta rajapinnasta." \
                  f" Päivitetty {date_} klo {hour_}.{minute_:02}."

    if option == 'total':
        size_col = 'active'

        data = get_data(
            '2020-03-01',
            date_,
            cumulative=True,
        )

    else:
        size_col = 'confirmed'

        data = get_data(
            '2020-03-01',
            date_,
            cumulative=False,
        )

    fig1 = px.scatter_mapbox(
        data,
        lat='lat',
        lon='lon',
        color='shp',
        hover_name='shp',
        hover_data='confirmed deaths recovered'.split(),
        size=size_col,
        animation_frame='pvm',
        center={'lat': 63.4, 'lon': 26.0},
        zoom=4,
        size_max=30,
        height=600,
        width=None,
        opacity=OPACITY,
    )
    fig1.update_layout(mapbox_style="carto-darkmatter")

    fig2 = px.bar(
        data,
        x='pvm',
        y=size_col,
        color='shp',
        hover_name="shp",
        height=520,
        width=None,
        opacity=OPACITY,
    )

    return fig1, fig2, update_time


if __name__ == '__main__':
    app.run_server(
        port=8080,
        host='0.0.0.0',
        debug=True,
    )
