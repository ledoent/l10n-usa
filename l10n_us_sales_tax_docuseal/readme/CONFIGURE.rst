#. Go to *Accounting > Configuration > Settings* and open the
   *Tax Exemption (DocuSeal)* section.
#. Set the **DocuSeal URL** (e.g. ``https://docuseal.example.com``) and an
   **API Token** (DocuSeal: *Settings > API*).
#. Set a **Default Exemption Template** id — the DocuSeal template used to
   generate certificates. Templates with fields named ``Company``, ``Name``,
   ``Email``, ``State`` and ``Exemption Number`` are pre-filled automatically.
#. Optionally set a **Webhook Signing Secret** matching the HMAC secret
   configured on the DocuSeal webhook for signature verification.
#. In DocuSeal, add a webhook pointing at
   ``https://<your-odoo-host>/docuseal/webhook`` for the *form.completed*
   event.
