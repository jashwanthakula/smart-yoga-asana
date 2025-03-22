import smtplib
from io import BytesIO
from pymongo import MongoClient
import faiss
import requests
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Image, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from sentence_transformers import SentenceTransformer

class YogaAsanaRecommender:
    def __init__(self, db_uri, db_name, collection_name):
        self.client = MongoClient(db_uri)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]

        # ✅ Load required fields from MongoDB
        self.asanas = list(self.collection.find({}, {"asana": 1, "age": 1, "gender": 1, "health_benefits": 1, 
                                                     "pose_direction": 1, "contraindications": 1, "image_url": 1}))

        self.asana_map = {}
        self.health_benefits = set()
        for asana in self.asanas:
            for benefit in asana.get("health_benefits", []):
                self.health_benefits.add(benefit)
                self.asana_map.setdefault(benefit, []).append(asana)
        
        self.health_benefits = list(self.health_benefits)  # Convert set to list
        self.model = None  # ✅ Lazy loading model
        self.index = None  # ✅ FAISS index delayed initialization

    def load_model(self):
        """Loads the SentenceTransformer model from Hugging Face."""
        if self.model is None:
            self.model = SentenceTransformer("jashwanthakula26/yoga-asana-model")  # ✅ Directly load from Hugging Face
            print("✅ Model loaded successfully from Hugging Face!")

    def build_faiss_index(self):
        """Builds the FAISS index for health benefits."""
        if self.index is None:
            self.load_model()
            embeddings = self.model.encode(self.health_benefits, convert_to_numpy=True)
            self.index = faiss.IndexFlatL2(embeddings.shape[1])
            self.index.add(embeddings)

    def find_all_matching_benefits(self, user_input, similarity_threshold=0.6):
        """Finds health benefits similar to user input."""
        self.build_faiss_index()
        input_embedding = self.model.encode([user_input], convert_to_numpy=True)
        distances, indices = self.index.search(input_embedding, len(self.health_benefits))

        return [self.health_benefits[idx] for dist, idx in zip(distances[0], indices[0]) if dist < similarity_threshold]

    def recommend_asanas(self, user_input, age, gender):
        """Recommends asanas based on matched health benefits."""
        matching_benefits = self.find_all_matching_benefits(user_input)
        seen_asanas = set()
        recommended_asanas = []

        for benefit in matching_benefits:
            for asana in self.asana_map.get(benefit, []):
                try:
                    asana_age = int(asana.get("age", 0))
                except ValueError:
                    asana_age = 0  # Treat 'All' as valid for all ages
                
                if asana_age <= int(age) and (asana.get("gender", "all").lower() == gender or asana["gender"].lower() == "all"):
                    if asana["_id"] not in seen_asanas:
                        seen_asanas.add(asana["_id"])
                        recommended_asanas.append(asana)
        
        return recommended_asanas

    def fetch_image(self, url):
        """Fetches an image from a URL and returns a BytesIO stream."""
        try:
            response = requests.get(url, stream=True)
            if response.status_code == 200:
                image_stream = BytesIO(response.content)
                return image_stream
        except Exception as e:
            print(f"⚠️ Could not fetch image {url}: {e}")
        return None

    def generate_pdf_in_memory(self, recommendations):
        """Generates a PDF report of recommended asanas with borders."""
        pdf_buffer = BytesIO()
        doc = SimpleDocTemplate(pdf_buffer, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()

        for asana in recommendations:
            # Title
            elements.append(Paragraph(f"<b>{asana.get('asana', 'Unknown Asana')}</b>", styles["Title"]))
            elements.append(Spacer(1, 10))

            # Embed Image
            image_url = asana.get("image_url", "")
            if image_url:
                image_stream = self.fetch_image(image_url)
                if image_stream:
                    img = Image(image_stream, width=250, height=150)
                    elements.append(img)
                    elements.append(Spacer(1, 10))

            # Steps to Perform
            elements.append(Paragraph("<b>Steps to Perform:</b>", styles["Heading3"]))
            for step in asana.get("pose_direction", []):
                elements.append(Paragraph(f"• {step}", styles["BodyText"]))

            # Contraindications
            elements.append(Spacer(1, 10))
            elements.append(Paragraph("<b>Contraindications:</b>", styles["Heading3"]))
            for contraindication in asana.get("contraindications", []):
                elements.append(Paragraph(f"• {contraindication}", styles["BodyText"]))

            # ✅ Ensure every asana starts on a new page
            elements.append(PageBreak())

        # Build PDF
        doc.build(elements, onFirstPage=self.add_page_border, onLaterPages=self.add_page_border)
        pdf_buffer.seek(0)
        return pdf_buffer

    def add_page_border(self, canvas, doc):
        """Adds a border to each page."""
        canvas.setStrokeColor(colors.black)
        canvas.setLineWidth(2)
        margin = 20  # Margin from edges
        width, height = letter
        canvas.rect(margin, margin, width - 2 * margin, height - 2 * margin)

    def send_email(self, user_email, pdf_stream):
        """Sends an email with the recommended asanas PDF attached."""
        sender_email = "jahnaviproject7@gmail.com"
        sender_password = "iwlw hosy ifat lfmd"

        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = user_email
        msg["Subject"] = "Your Recommended Yoga Asanas"

        part = MIMEBase("application", "octet-stream")
        part.set_payload(pdf_stream.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment; filename=recommended_asanas.pdf")
        msg.attach(part)

        try:
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(sender_email, sender_password)
                server.sendmail(sender_email, user_email, msg.as_string())
            print("✅ PDF has been mailed successfully!")
        except Exception as e:
            print(f"❌ Error sending email: {e}")
