from flask import Flask, render_template, request, jsonify
from yoga_recommender import YogaAsanaRecommender
from pymongo import MongoClient
import random
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# ✅ Database Configuration
DB_URI = os.getenv("DB_URI")
DB_NAME = "yoga_asana"
COLLECTION_NAME = "asana_list"
QUOTES_COLLECTION_NAME = "yoga_quotes"

# ✅ Initialize Recommender
recommender = YogaAsanaRecommender(DB_URI, DB_NAME, COLLECTION_NAME)

# ✅ Connect to MongoDB for Quotes
try:
    client = MongoClient(DB_URI)
    db = client[DB_NAME]
    quotes_collection = db[QUOTES_COLLECTION_NAME]
    print("✅ Connected to MongoDB successfully!")
except Exception as e:
    print(f"❌ Error connecting to MongoDB: {e}")

@app.route('/')
def index():
    """
    Render the home page of the web application
    with 3 random yoga quotes from MongoDB.
    """
    try:
        # ✅ Fetch the quotes document from MongoDB
        quotes_document = quotes_collection.find_one({}, {'_id': 0})  # Exclude the _id field

        # ✅ Randomly select 3 quotes
        if quotes_document and 'quotes' in quotes_document:
            all_quotes = quotes_document['quotes']
            random_quotes = random.sample(all_quotes, min(3, len(all_quotes)))  # Select up to 3 quotes
        else:
            random_quotes = ["No quotes available."] * 3
    except Exception as e:
        print(f"❌ Error fetching quotes: {e}")
        random_quotes = ["Error loading quotes."] * 3

    return render_template('index.html', quotes=random_quotes)


@app.route('/recommend')
def recommend():
    """
    Render the recommendation form page.
    """
    return render_template('recommend.html')


@app.route('/get_recommendations', methods=['POST'])
def get_recommendations():
    """
    Handle the form submission, generate recommendations, and send the email.
    """
    user_email = request.form['email']
    age = request.form['age']
    gender = request.form['gender']
    health_issue = request.form.get('health_issue')

    # ✅ Generate Yoga Recommendations
    recommendations = recommender.recommend_asanas(health_issue, age, gender)

    if recommendations:
        # ✅ Generate PDF & Email
        try:
            pdf_stream = recommender.generate_pdf_in_memory(recommendations)
            recommender.send_email(user_email, pdf_stream)
            return jsonify({"success": True, "message": "Recommendations sent successfully!"})
        except Exception as e:
            print(f"❌ Error generating/sending email: {e}")
            return jsonify({"success": False, "message": "Error sending recommendations."})
    else:
        return jsonify({"success": False, "message": "No suitable yoga asanas found."})


if __name__ == '__main__':
    app.run(debug=True)