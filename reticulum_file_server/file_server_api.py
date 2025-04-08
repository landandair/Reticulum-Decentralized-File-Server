from threading import Thread

import flask
from flask_classful import FlaskView, request, route

class RNFSView(FlaskView):
    def __init__(self, server_info):
        self.info = server_info

    def index(self):
        return ('''<h1>Reticulum File Server API: Running</h1>
        
                ''')

    @route("/site-map")
    def site_map(self):
        links = []
        # for rule in .url_map.iter_rules():
        #     # Filter out rules we can't navigate to in a browser
        #     # and rules that require parameters
        #     if "GET" in rule.methods and has_no_empty_params(rule):
        #         url = url_for(rule.endpoint, **(rule.defaults or {}))
        #         links.append((url, rule.endpoint))

    @route('/getNode/<id>', methods=['GET'], endpoint='getNode')
    def get_node(self, id=None):
        """Return node information associated with hash provided TODO:Make this a file download if the data is not json"""
        if id == 'root':
            id = None
        print(id)
        return self.info.get_node_info(id)

    @route('/getSrc', methods=['GET'], endpoint='getSrc')
    def get_src(self):
        """Get source dest hash useful for knowing which data tree you can add to"""
        return self.info.get_src_dest()

    @route('/uploadData', methods=['GET', 'POST'], endpoint='uploadData')
    def upload_data(self):
        """Get a file from destination add it to data store"""
        if request.method == 'POST':
            # check if the post request has the file part
            if 'file' not in request.files:
                flask.flash('No file part')
                return flask.redirect(request.url)
            file = request.files['file']
            parent = request.form['parent']
            # if user does not select file, browser also
            # submit an empty part without filename
            if file.filename == '':
                flask.flash('No selected file')
                return flask.redirect(request.url)
            if file:
                self.info.upload_file(file.filename, file.stream.read(), parent)
                return flask.redirect(flask.url_for('uploadData',
                                        filename=file.filename))
        return '''
            <!doctype html>
            <title>Upload new File</title>
            <h1>Upload new File</h1>
            <form method=post enctype=multipart/form-data>
              <input type=file name=file>
              <input type=text name=parent>
              <input type=submit value=Upload>
            </form>
            '''  # Html for making basic file upload

    @route('/mkdir', methods=['GET', 'POST'], endpoint='mkdir')
    def make_directory(self):
        """make a new folder node in data store"""
        if request.method == 'POST':
            name = request.form['name']
            parent = request.form['parent']
            # if user does not select file, browser also
            # submit an empty part without filename
            if not name:
                flask.flash('No name provided')
                return flask.redirect(request.url)
            else:
                self.info.make_dir(name, parent)
                return flask.redirect(flask.url_for('mkdir'))
        return '''
            <!doctype html>
            <title>Make new Folder</title>
            <h1>Add Name and parent node</h1>
            <form method=post enctype=multipart/form-data>
              <input type=text name=name>
              <input type=text name=parent>
              <input type=submit value=Upload>
            </form>
            '''  # Html for making basic file upload


def start_server_thread(server_info):
    t = Thread(target=start_server, args=[server_info], daemon=True)
    t.start()


def start_server(server_info):
    """Put api on different thread"""
    app = flask.Flask(__name__)
    RNFSView.register(app, route_base='/', init_argument=server_info)
    host, port = server_info.get_address()
    app.run(host, port, debug=False)
