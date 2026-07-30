1. Go to *Settings → US Sales Tax → DocuSeal E-Signature* and fill in the
   instance URL, an API token, and the id of the template to send.
2. Set a webhook secret, and configure the same secret in DocuSeal against a
   `form.completed` webhook pointing at `https://<your-odoo>/docuseal/webhook`.
   Leaving it empty accepts unverified deliveries — only ever reasonable on a
   trusted network.
3. The template needs three fields, named exactly: **State**, **Exemption
   Type** and **Exemption Number**. *Exemption Type* must carry an exemption
   reason code (`resale`, `agriculture`, …).
