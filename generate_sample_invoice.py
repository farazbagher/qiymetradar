import sys
import os

# Path to the backend folder so we can import app.docs.invoicegen
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.docs.invoicegen import make_invoice, render_lines, to_pdf_bytes

# Generate a sample invoice
seed = 42
template = "A" # Template A is a standard Azerbaijani invoice
inv = make_invoice(seed, template)
lines = render_lines(inv, template)
pdf_data = to_pdf_bytes(lines)

# Save to a file
with open("sample_invoice.pdf", "wb") as f:
    f.write(pdf_data)

print("Successfully created sample_invoice.pdf")
