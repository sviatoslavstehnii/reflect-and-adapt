import csv
import smtplib
from datetime import date

def main():
    total = 0
    count = 0
    big = []

    f = open("transactions.csv")
    reader = csv.DictReader(f)
    for row in reader:
        amount = float(row["amount"])
        total = total + amount
        count = count + 1
        if amount > 500:
            big.append(row)

    avg = total / count
    subject = "Daily Report " + str(date.today())
    body = "Transactions: " + str(count) + "\nTotal: " + str(total) + "\nAverage: " + str(avg)

    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.login("aisha@teamflow.io", "mypassword123")
    server.sendmail("aisha@teamflow.io", "team@teamflow.io", subject + "\n\n" + body)
    server.quit()

main()
