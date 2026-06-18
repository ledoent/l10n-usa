This module manages US sales-tax exemption certificates collected from
customers and signed through `DocuSeal <https://www.docuseal.com>`_.

It provides a generic exemption-certificate record on the customer, an action
to send the certificate to the customer for e-signature via DocuSeal, and a
webhook that files the signed PDF back on the certificate and tracks its
validity and expiration.

It is a stand-alone DocuSeal connector with no dependency on any proprietary
tax engine, so it can be used alongside an existing ``sign_oca`` based flow.
