"""download documents from o2online.de"""

import itertools
import click
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import docdl
import docdl.util


class O2(docdl.SeleniumWebPortal):
    """download documents from o2online.de"""
    URL_LOGIN="https://login.o2online.de/auth/login"
    URL_LOGOUT="https://login.o2online.de/auth/logout"
    URL_MY_MESSAGES="https://www.o2online.de/ecareng/my-messages"
    URL_INVOICES="https://www.o2online.de/vt-billing/api/invoiceinfo"
    URL_INVOICE="https://www.o2online.de/vt-billing/api/billdocument"
    URL_INVOICE_OVERVIEW="https://www.o2online.de/vt-billing/api/invoiceoverview"
    URL_VALUE_ADDED_INVOICE="https://www.o2online.de/vt-billing/api/value-added-services-invoices"

    def login(self):
        """authenticate"""
        self.webdriver.get(self.URL_LOGIN)
        # find entry field
        username = self.webdriver.find_element(
            By.XPATH,
            "//input[@name='IDToken1']"
        )
        # wait for entry field
        WebDriverWait(self.webdriver, self.TIMEOUT).until(
            EC.visibility_of(username)
        )
        # send username
        username.send_keys(self.login_id)
        # save current URL
        current_url = self.webdriver.current_url
        # submit form
        username.submit()
        # wait for page to load
        current_url = self.wait_for_urlchange(current_url)
        # find entry field
        password = self.webdriver.find_element(
            By.XPATH,
            "//input[@name='IDToken1']"
        )
        # wait for entry field
        WebDriverWait(self.webdriver, self.TIMEOUT).until(
            EC.visibility_of(password)
        )
        # send password
        password.send_keys(self.password)
        # submit form
        password.submit()
        # wait for page to load
        current_url = self.wait_for_urlchange(current_url)
        # wait for either login success or failure
        WebDriverWait(self.webdriver, self.TIMEOUT).until(
            lambda d: "Mein o2" in d.title or "Login" in d.title
        )
        # Login failed
        return "Login" not in self.webdriver.title

    def logout(self):
        self.webdriver.get(self.URL_LOGOUT)

    def documents(self):
        """fetch list of documents"""
        for i, document in enumerate(
            itertools.chain(self.invoices(), self.invoice_overview())
        ):
            # set an id
            document.attributes['id'] = i
            # return document
            yield document

    def invoice_overview(self):
        """fetch invoice overview"""
        req = self.session.get(self.URL_INVOICE_OVERVIEW)
        invoiceoverview = req.json()
        years = invoiceoverview['invoices'].keys()
        for year in years:
            yield docdl.Document(
                url=f"{self.URL_INVOICE_OVERVIEW}?statementYear={year}",
                request_headers={ "Accept": "application/pdf" },
                attributes={
                    'category': "invoice_overview",
                    'year': year,
                    'date': docdl.util.parse_date(f"{year}-01-01"),
                    'filename': f"o2-{year}-rechnungsübersicht.pdf"
                }
            )

    def invoices(self):
        """fetch list of invoices"""
        # fetch normal invoices
        req = self.session.get(self.URL_INVOICES)
        for document in self.parse_invoices_json(req.json()):
            document.attributes['category'] = "invoice"
            yield document
        # fetch value added invoices
        req = self.session.get(self.URL_VALUE_ADDED_INVOICE)
        for document in self.parse_invoices_json(req.json()):
            document.attributes['category'] = "value_added_invoice"
            yield document

    def parse_invoices_json(self, invoices):
        """parse all documents in invoiceinfo json"""
        # iterate all invoices
        for invoice in invoices['invoices']:
            year = invoice['date'][0]
            month = invoice['date'][1]
            day = invoice['date'][2]
            amount = invoice['total']['amount']
            # ~ currency = invoice['total']['currency']
            # collect attributes
            attributes = {
                'amount': f"{amount}",
                'date': docdl.util.parse_date(f"{year}-{month}-{day}")
            }
            # iterate documents in this invoice
            for document in invoice['billDocuments']:
                category = document['documentType'].lower()
                yield docdl.Document(
                    url=f"{self.URL_INVOICE}?" \
                        f"billNumber={document['billNumber']}&" \
                        f"documentType={document['documentType']}",
                    attributes={
                        **attributes,
                        'number': document['billNumber'],
                        'doctype': document['documentType'],
                        'filename': f"o2-{year}-{month}-{day}-{category}.pdf"
                    }
                )

@click.command()
@click.pass_context
# pylint: disable=C0103
def o2(ctx):
    """o2online.de (invoices/postbox)"""
    docdl.cli.run(ctx, O2)
