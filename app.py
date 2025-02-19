import dash
import dash_core_components as dcc
import dash_html_components as html
import dash_leaflet as dl
import dash_leaflet.express as dlx
import db
import numpy as np
import pandas as pd
import plotly.express as px

from dash.dependencies import Output, Input
from dash_extensions.javascript import assign

TITLE = 'Ribbit Network'
REFRESH_MS = 60 * 1000

chroma = 'https://cdnjs.cloudflare.com/ajax/libs/chroma-js/2.1.0/chroma.min.js'
colorscale = ['lightgreen', 'green', 'darkgreen', 'black']

# Dash App
app = dash.Dash(__name__, title=TITLE, update_title=None, external_scripts=[chroma])
server = app.server

sensor_data = pd.DataFrame(columns=['Time', 'CO₂ (PPM)', 'Temperature (°C)', 'Barometric Pressure (mBar)', 'Humidity (%)'])


def serve_layout():
    df = db.get_map_data()
    zoom, b_box_lat, b_box_lon = get_plotting_zoom_level_and_center_coordinates_from_lonlat_tuples(longitudes=df['lon'],
                                                                                                   latitudes=df['lat'])

    return html.Div([
        html.Div(id='onload', hidden=True),
        dcc.Interval(id='interval', interval=REFRESH_MS, n_intervals=0),

        html.Div([
            html.Img(src='assets/frog.svg'),
            html.H1(TITLE),
            html.A(html.H3('Learn'), href='https://ribbitnetwork.org/',
                   style={'margin-left': 'auto', 'text-decoration': 'underline', 'color': 'black'}),
            html.A(html.H3('Build'),
                   href='https://github.com/Ribbit-Network/ribbit-network-frog-sensor#build-a-frog',
                   style={'margin-left': '2em', 'text-decoration': 'underline', 'color': 'black'}),
            html.A(html.H3('Order'),
                   href='https://ribbitnetwork.org/#buy',
                   style={'margin-left': '2em', 'text-decoration': 'underline', 'color': 'black'}),
            html.A(html.H3('Support'), href='https://ko-fi.com/keenanjohnson',
                   style={'margin-left': '2em', 'text-decoration': 'underline', 'color': 'black'}),
        ], id='nav'),

        html.Div([
            dl.Map(
                [
                    dl.TileLayer(url='https://cartodb-basemaps-{s}.global.ssl.fastly.net/light_all/{z}/{x}/{y}.png',
                                 attribution='Map tiles by Carto, under CC BY 3.0. Data by OpenStreetMap, under ODbL.'),
                    dl.GeoJSON(id='geojson'),
                    dl.Colorbar(colorscale=colorscale, width=20, height=200, min=300, max=600, unit='PPM'),
                    dl.GestureHandling(),
                ],
                id='map',
                center=(b_box_lat, b_box_lon),
                zoom=zoom,
            ),
        ], id='map-container'),

        html.Div([
            dcc.Dropdown(id='duration', clearable=False, searchable=False, value='24h', options=[
                {'label': '10 minutes', 'value': '10m'},
                {'label': '30 minutes', 'value': '30m'},
                {'label': '1 hour', 'value': '1h'},
                {'label': '1 day', 'value': '24h'},
                {'label': '7 days', 'value': '7d'},
                {'label': '30 days', 'value': '30d'},
            ]),
            html.Div([
                html.Button(html.Div([
                    html.Img(src='assets/download.svg'),
                    'Export as CSV',
                ]), id='export'),
                dcc.Download(id='download'),
            ]),
        ], id='controls'),

        html.Div([
            dcc.Graph(id='co2_graph'),
            dcc.Graph(id='temp_graph'),
            dcc.Graph(id='baro_graph'),
            dcc.Graph(id='humidity_graph'),
            html.Div(id='timezone', hidden=True),
        ], id='graphs'),
    ])


def get_plotting_zoom_level_and_center_coordinates_from_lonlat_tuples(longitudes=None, latitudes=None):
    """
    Basic framework adopted from Krichardson under the following thread:
    https://community.plotly.com/t/dynamic-zoom-for-mapbox/32658/7

    # NOTE: THIS IS A TEMPORARY SOLUTION UNTIL THE DASH TEAM IMPLEMENTS DYNAMIC ZOOM
    # in their plotly-functions associated with mapbox, such as go.Densitymapbox() etc.

    Returns the appropriate zoom-level for these plotly-mapbox-graphics along with
    the center coordinates of all provided coordinate tuples.
    """

    # Check whether both latitudes and longitudes have been passed,
    # or if the list lengths don't match
    if ((latitudes is None or longitudes is None)
            or (len(latitudes) != len(longitudes))):
        # Otherwise, return the default values of 0 zoom and the coordinate origin as center point
        return 0, (0, 0)

    # Get the boundary-box 
    b_box = {
        'height': latitudes.max() - latitudes.min(),
        'width': longitudes.max() - longitudes.min(),
        'center_lat': np.mean(latitudes),
        'center_lon': np.mean(longitudes)
    }

    # get the area of the bounding box in order to calculate a zoom-level
    area = b_box['height'] * b_box['width']

    # * 1D-linear interpolation with numpy:
    # - Pass the area as the only x-value and not as a list, in order to return a scalar as well
    # - The x-points "xp" should be in parts in comparable order of magnitude of the given area
    # - The zoom-levels are adapted to the areas, i.e. start with the smallest area possible of 0
    # which leads to the highest possible zoom value 20, and so forth decreasing with increasing areas
    # as these variables are anti-proportional
    zoom = np.interp(x=area,
                     xp=[0, 5 ** -10, 4 ** -10, 3 ** -10, 2 ** -10, 1 ** -10, 1 ** -5],
                     fp=[20, 15, 14, 13, 11, 6, 4])

    # Finally, return the zoom level and the associated boundary-box center coordinates
    return zoom, b_box['center_lat'], b_box['center_lon']


app.layout = serve_layout

# Get browser timezone
app.clientside_callback(
    '''
    function(n_intervals) {
        return Intl.DateTimeFormat().resolvedOptions().timeZone
    }
    ''',
    Output('timezone', 'children'),
    Input('onload', 'children'),
)

point_to_layer = assign('''function(feature, latlng, context) {
    const {min, max, colorscale, circleOptions, colorProp} = context.props.hideout;
    const csc = chroma.scale(colorscale).domain([min, max]);
    circleOptions.fillColor = csc(feature.properties[colorProp]);
    return L.circleMarker(latlng, circleOptions);
}''')

cluster_to_layer = assign('''function(feature, latlng, index, context) {
    const {min, max, colorscale, circleOptions, colorProp} = context.props.hideout;
    const csc = chroma.scale(colorscale).domain([min, max]);
    // Set color based on mean value of leaves.
    const leaves = index.getLeaves(feature.properties.cluster_id);
    let valueSum = 0;
    for (let i = 0; i < leaves.length; ++i) {
        valueSum += leaves[i].properties[colorProp]
    }
    const valueMean = valueSum / leaves.length;
    // Render a circle with the number of leaves written in the center.
    const icon = L.divIcon.scatter({
        html: '<div style="background-color:white;"><span>' + feature.properties.point_count_abbreviated + '</span></div>',
        className: "marker-cluster",
        iconSize: L.point(40, 40),
        color: csc(valueMean)
    });
    return L.marker(latlng, {icon : icon})
}''')


# Update the Map
@app.callback(
    Output('geojson', 'children'),
    [
        Input('onload', 'children'),
        Input('interval', 'n_intervals'),
    ],
)
def update_map(_children, _n_intervals):
    df = db.get_map_data()
    df['tooltip'] = df['co2'].round(decimals=2).astype(str) + ' PPM'

    return dl.GeoJSON(
        id='geojson',
        data=dlx.dicts_to_geojson(df.to_dict('records')),
        options=dict(pointToLayer=point_to_layer),
        cluster=True,
        clusterToLayer=cluster_to_layer,
        zoomToBoundsOnClick=True,
        superClusterOptions=dict(radius=100),
        hideout=dict(colorProp='co2', circleOptions=dict(fillOpacity=1, stroke=False, radius=8), min=300, max=600,
                     colorscale=colorscale),
    )


# Update Data Plots
@app.callback(
    Output('co2_graph', 'figure'),
    Output('temp_graph', 'figure'),
    Output('baro_graph', 'figure'),
    Output('humidity_graph', 'figure'),
    [
        Input('timezone', 'children'),
        Input('duration', 'value'),
        Input('geojson', 'click_feature'),
        Input('interval', 'n_intervals'),
    ],
)
def update_graphs(timezone, duration, click_feature, _n_intervals):
    global sensor_data

    if click_feature is not None:
        sensor = click_feature.get('properties', {}).get('host', None)
        if sensor is not None:
            sensor_data = db.get_sensor_data(sensor, duration)
            sensor_data.rename(
                columns={'_time': 'Time', 'co2': 'CO₂ (PPM)', 'humidity': 'Humidity (%)', 'lat': 'Latitude', 'lon': 'Longitude',
                         'alt': 'Altitude (m)', 'temperature': 'Temperature (°C)',
                         'baro_pressure': 'Barometric Pressure (mBar)'}, inplace=True)
            sensor_data['Time'] = sensor_data['Time'].dt.tz_convert(timezone)

    return (
       px.line(sensor_data, x='Time', y='CO₂ (PPM)', color_discrete_sequence=['black'], template='plotly_white',
               render_mode='svg', hover_data={'CO₂ (PPM)': ':.2f'}),
       px.line(sensor_data, x='Time', y='Temperature (°C)', color_discrete_sequence=['black'], template='plotly_white',
               render_mode='svg', hover_data={'Temperature (°C)': ':.2f'}),
       px.line(sensor_data, x='Time', y='Barometric Pressure (mBar)', color_discrete_sequence=['black'],
               template='plotly_white', render_mode='svg', hover_data={'Barometric Pressure (mBar)': ':.2f'}),
       px.line(sensor_data, x='Time', y='Humidity (%)', color_discrete_sequence=['black'], template='plotly_white',
               render_mode='svg', hover_data={'Humidity (%)': ':.2f'}),
    )


# Export data as CSV
@app.callback(
    Output('download', 'data'),
    Input('export', 'n_clicks'),
)
def export_data(n_clicks):
    if n_clicks is None or sensor_data.empty:
        return

    return dcc.send_data_frame(sensor_data.to_csv, index=False, filename='data.csv')


if __name__ == '__main__':
    app.run_server(debug=True)
