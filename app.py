from flask import Flask
import threading
import os
from bot import main   # bot.py থেকে main ফাংশন ইমপোর্ট

app = Flask(__name__)

@app.route("/")
def home():
    return "OTP Bot Running"

def run_bot():
    main()  # আলাদা থ্রেডে বট চালাবে

if __name__ == "__main__":
    t = threading.Thread(target=run_bot)
    t.start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)