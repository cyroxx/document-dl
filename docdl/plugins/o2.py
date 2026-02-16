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

    URL_BASE = "https://www.o2online.de"
    URL_BILLING = f"{URL_BASE}/vt-billing/api"
    URL_LOGIN = "https://login.o2online.de/auth/login"
    URL_LOGOUT = "https://login.o2online.de/auth/logout"
    URL_INVOICES = f"{URL_BASE}/mein-o2/rechnung/"
    URL_MY_MESSAGES = f"{URL_BASE}/ecareng/my-messages"
    URL_INVOICE_INFO = f"{URL_BILLING}/invoiceinfo"
    URL_INVOICE = f"{URL_BILLING}/billdocument"
    URL_INVOICE_OVERVIEW = f"{URL_BILLING}/invoiceoverview"
    URL_VALUE_ADDED_INVOICE = f"{URL_BILLING}/value-added-services-invoices"

    def login(self):
        """authenticate"""
        self.webdriver.get(self.URL_LOGIN)
        
        # find entry field
        # (the login form is inside a shadow DOM, so we have to get inside it first)
        shadow_host = WebDriverWait(self.webdriver, self.TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "one-input#idToken4_od"))
        )
        shadow_root = shadow_host.shadow_root
        username = shadow_root.find_element(By.CSS_SELECTOR, "input")

        # send username
        username.send_keys(self.login_id)
        # save current URL
        current_url = self.webdriver.current_url
        
        # submit form (Button "Weiter")
        submit_button = WebDriverWait(self.webdriver, self.TIMEOUT).until(
            EC.element_to_be_clickable((By.ID, "IDToken5_4_od_0"))
        )

        submit_button.click()

        # wait for either password prompt or failure message
        # TODO: wait for failure
        pw_shadow_host = WebDriverWait(self.webdriver, self.TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "one-input#idToken5_od"))
        )
        # find entry field
        password = pw_shadow_host.shadow_root.find_element(By.CSS_SELECTOR, "input[type='password']")

        # send password
        password.send_keys(self.password)
        # submit form
        login_btn = WebDriverWait(self.webdriver, self.TIMEOUT).until(
            EC.element_to_be_clickable((By.ID, "IDToken6_5_od_1"))
        )

        login_btn.click()

        # wait for page to load
        current_url = self.wait_for_urlchange(current_url)
        # wait for cookie-banner container
        WebDriverWait(self.webdriver, self.TIMEOUT).until(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    "//div[@id='usercentrics-root'] | "
                    "//div[contains(@data-test-id, 'unified-login-error')]",
                )
            )
        )
        # get cookie-banner container
        if container := self.webdriver.find_element(
            By.XPATH, "//div[@id='usercentrics-root']"
        ):
            # get inside DOM element so we can use XPATH
            container = container.shadow_root.find_element(By.CSS_SELECTOR, "section")

            # wait for cookie banner
            WebDriverWait(container, self.TIMEOUT).until(
                EC.visibility_of_element_located(
                    (By.XPATH, ".//button[contains(text(), 'Verweigern')]")
                )
            )
            # click "reject" button if there is one
            button = container.find_element(
                By.XPATH, ".//button[contains(text(), 'Verweigern')]"
            )
            button.click()

        # click "close" button if there is one
        closebutton = self.webdriver.find_elements(
            By.XPATH, "//button[contains(text(), 'Schließen')]"
        )
        if closebutton:
            closebutton.click()

        # Login failed
        return self.webdriver.find_elements(
            By.XPATH, "//a[contains(@href, 'auth/logout')]"
        )

    def logout(self):
        self.webdriver.get(self.URL_LOGOUT)

    def documents(self):
        """fetch list of documents"""
        for i, document in enumerate(
            itertools.chain(self.invoices(), self.invoice_overview())
        ):
            # set an id
            document.attributes["id"] = i
            # return document
            yield document

    def invoice_overview(self):
        """fetch invoice overview"""
        # copy cookies to request session
        self.copy_to_requests_session()
        req = self.session.get(self.URL_INVOICE_OVERVIEW)
        assert req.status_code == 200
        invoiceoverview = req.json()
        years = invoiceoverview["invoices"].keys()
        for year in years:
            yield docdl.Document(
                url=f"{self.URL_INVOICE_OVERVIEW}?statementYear={year}",
                request_headers={"Accept": "application/pdf"},
                attributes={
                    "category": "invoice_overview",
                    "year": year,
                    "date": docdl.util.parse_date(f"{year}-01-01"),
                    "filename": f"o2-{year}-rechnungsübersicht.pdf",
                },
            )

    def invoices(self):
        """fetch list of invoices"""
        # save current URL
        current_url = self.webdriver.current_url
        # fetch normal invoices
        self.webdriver.get(self.URL_INVOICES)
        # wait for page to load
        current_url = self.wait_for_urlchange(current_url)
        # copy cookies to request session
        self.copy_to_requests_session()
        # load invoice info json
        req = self.session.get(self.URL_INVOICE_INFO)
        for document in self.parse_invoices_json(req.json()):
            document.attributes["category"] = "invoice"
            yield document
        # fetch value added invoices
        req = self.session.get(self.URL_VALUE_ADDED_INVOICE)
        for document in self.parse_invoices_json(req.json()):
            document.attributes["category"] = "value_added_invoice"
            yield document

    def parse_invoices_json(self, invoices):
        """parse all documents in invoiceinfo json"""
        # iterate all invoices
        for invoice in invoices["invoices"]:
            year = invoice["date"][0]
            month = invoice["date"][1]
            day = invoice["date"][2]
            amount = invoice["total"]["amount"]
            # ~ currency = invoice['total']['currency']
            # collect attributes
            attributes = {
                "amount": f"{amount}",
                "date": docdl.util.parse_date(f"{year}-{month}-{day}"),
            }
            # iterate documents in this invoice
            for document in invoice["billDocuments"]:
                category = document["documentType"].lower()
                yield docdl.Document(
                    url=f"{self.URL_INVOICE}?"
                    f"billNumber={document['billNumber']}&"
                    f"documentType={document['documentType']}",
                    attributes={
                        **attributes,
                        "number": document["billNumber"],
                        "category": document["documentType"],
                        "filename": f"o2-{year}-{month}-{day}-{category}.pdf",
                    },
                )


@click.command()
@click.pass_context
# pylint: disable=C0103
def o2(ctx):
    """o2online.de (invoices, call record, postbox)"""
    docdl.cli.run(ctx, O2)
