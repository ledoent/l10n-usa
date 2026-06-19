#. Open a customer, or go to *Accounting > Customers > Exemption Certificates*.
#. Create a certificate: pick the customer, jurisdiction (state) and type.
#. Click **Send for Signature**. A DocuSeal submission is created from the
   template and emailed to the customer; the certificate moves to *Sent*.
#. When the customer signs, DocuSeal calls the webhook: the signed PDF is
   stored on the certificate, the state becomes *Signed* and validity is
   computed from the expiration date.
#. A daily scheduled action moves past-expiration certificates to *Expired*.

Customers with at least one valid certificate are flagged via the
*Has Valid Exemption* field, which is searchable for reporting.
