from flask import *


app = Flask(__name__)


@app.route("/")
def home():
    '''
    redirect user to index.html aka sign-in page
    '''
    return redirect("/index.html")


@app.route("/index.html")
def index():
    return render_template("index.html")


@app.route("/sign-up.html")
def sign_up():
    return render_template("sign-up.html")


@app.route("/nav.html")
def nav():
    return render_template("nav.html")


def main():
    app.run()


if __name__ == '__main__':
    main()
