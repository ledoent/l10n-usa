1. Build a `sign_oca` template for your exemption certificate, with three
   fields named exactly **State**, **Exemption Type** and **Exemption Number**.
   *Exemption Type* must carry an exemption reason code (`resale`,
   `agriculture`, …).
2. Set the template's signer role to resolve the customer from the record —
   an expression policy on `partner_id`.
3. On the company, set *Certificate Signature Backend* to **Sign Oca** and
   select the template.
