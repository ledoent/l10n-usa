/* Copyright 2026 Ledo Enterprises
 * License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
 *
 * Zift's proxynization, driven from Odoo's payment form.
 *
 * WHAT THIS IS, AND WHAT IT IS NOT
 *
 * Proxynization is not hosted fields. It reads the card or bank account out of
 * inputs on *this* page and exchanges them for a token. The details never
 * reach an Odoo server, but the PCI SSC's split is about whose code runs on
 * the capture page rather than where the data is posted: a merchant script is
 * SAQ A-EP. See readme/CONFIGURE.md — that posture was chosen deliberately.
 *
 * What leaves this file is a token, the accessory Zift needs to charge it
 * later (card expiry, or the ABA routing number), the account type and the
 * holder name. Never a card number and never an account number.
 */
/* global ZiftProxynization */

import {loadJS} from "@web/core/assets";
import {_t} from "@web/core/l10n/translation";
import {RPCError, rpc} from "@web/core/network/rpc";
import {patch} from "@web/core/utils/patch";

import {PaymentForm} from "@payment/interactions/payment_form";

/**
 * The ABA checksum: nine digits weighted 3-7-1 repeating, summing to a
 * multiple of ten.
 *
 * Checked here as well as on the server because it is the ONLY integrity check
 * available anywhere in an ACH debit. Zift verifies a bank account number by
 * length, where a card additionally gets Luhn — so a mistyped card fails at
 * the gateway and a mistyped bank account tokenizes cleanly and comes back as
 * a returned debit days later. Catching it at the keyboard is worth the
 * duplication.
 *
 * @param {String} routing - The routing number as typed.
 * @returns {Boolean} Whether the checksum holds.
 */
function isValidRoutingNumber(routing) {
    const digits = String(routing || "").replace(/\D/g, "");
    if (digits.length !== 9) {
        return false;
    }
    const weights = [3, 7, 1, 3, 7, 1, 3, 7, 1];
    let sum = 0;
    for (let i = 0; i < 9; i++) {
        sum += Number(digits.charAt(i)) * weights[i];
    }
    return sum % 10 === 0;
}

patch(PaymentForm.prototype, {
    setup() {
        super.setup();
        this.ziftData = {}; // Form data of each instantiated payment method.
    },

    // #=== DOM MANIPULATION ===#

    /**
     * Prepare the inline form of Zift for direct payment.
     *
     * @override method from payment.payment_form
     * @private
     * @param {Number} providerId - The id of the selected payment option's provider.
     * @param {String} providerCode - The code of the selected payment option's provider.
     * @param {Number} paymentOptionId - The id of the selected payment option.
     * @param {String} paymentMethodCode - The code of the selected payment method, if any.
     * @param {String} flow - The online payment flow of the selected payment option.
     * @returns {void}
     */
    async _prepareInlineForm(
        providerId,
        providerCode,
        paymentOptionId,
        paymentMethodCode,
        flow
    ) {
        if (providerCode !== "zift") {
            await super._prepareInlineForm(...arguments);
            return;
        }

        if (flow === "token") {
            return; // Don't show the form for tokens.
        } else if (this.ziftData[paymentOptionId]) {
            this._setPaymentFlow("direct");
            await loadJS(this.ziftData[paymentOptionId].proxynization_url);
            return;
        }

        this._setPaymentFlow("direct");

        const radio = document.querySelector('input[name="o_payment_radio"]:checked');
        const inlineForm = this._getInlineForm(radio);
        const ziftForm = inlineForm.querySelector('[name="o_zift_form"]');
        this.ziftData[paymentOptionId] = JSON.parse(
            ziftForm.dataset.ziftInlineFormValues
        );
        this.ziftData[paymentOptionId].form = ziftForm;

        await loadJS(this.ziftData[paymentOptionId].proxynization_url);
    },

    // #=== PAYMENT FLOW ===#

    /**
     * Validate the inline form before letting the generic flow start.
     *
     * @override method from payment.payment_form
     * @private
     * @param {String} providerCode - The code of the selected payment option's provider.
     * @param {Number} paymentOptionId - The id of the selected payment option.
     * @param {String} paymentMethodCode - The code of the selected payment method, if any.
     * @param {String} flow - The payment flow of the selected payment option.
     * @returns {void}
     */
    async _initiatePaymentFlow(providerCode, paymentOptionId, paymentMethodCode, flow) {
        if (providerCode !== "zift" || flow === "token") {
            await super._initiatePaymentFlow(...arguments);
            return;
        }

        const inputs = Object.values(
            this._ziftGetInlineFormInputs(paymentOptionId, paymentMethodCode)
        );
        if (!inputs.every((element) => element.reportValidity())) {
            this._enableButton();
            return;
        }

        if (paymentMethodCode !== "card") {
            const routing = this._ziftGetInlineFormInputs(
                paymentOptionId,
                paymentMethodCode
            ).abaNumber;
            if (!isValidRoutingNumber(routing.value)) {
                this._displayErrorDialog(
                    _t("Payment processing failed"),
                    _t("That is not a valid nine-digit routing number.")
                );
                this._enableButton();
                return;
            }
        }

        await super._initiatePaymentFlow(...arguments);
    },

    /**
     * Tokenize with Zift, then send the token to Odoo.
     *
     * @override method from payment.payment_form
     * @private
     * @param {String} providerCode - The code of the selected payment option's provider.
     * @param {Number} paymentOptionId - The id of the selected payment option.
     * @param {String} paymentMethodCode - The code of the selected payment method, if any.
     * @param {Object} processingValues - The processing values of the transaction.
     * @returns {void}
     */
    async _processDirectFlow(
        providerCode,
        paymentOptionId,
        paymentMethodCode,
        processingValues
    ) {
        if (providerCode !== "zift") {
            await super._processDirectFlow(...arguments);
            return;
        }

        let ziftData = null;
        try {
            ziftData = await this.waitFor(
                this._ziftTokenize(paymentOptionId, paymentMethodCode)
            );
        } catch (error) {
            this._displayErrorDialog(
                _t("Payment processing failed"),
                error.message ||
                    _t(
                        "Those payment details could not be read. Check them and try again."
                    )
            );
            this._enableButton();
            return;
        }

        try {
            await this.waitFor(
                rpc("/payment/zift/payment", {
                    reference: processingValues.reference,
                    partner_id: processingValues.partner_id,
                    access_token: processingValues.access_token,
                    zift_data: ziftData,
                })
            );
            window.location = "/payment/status";
        } catch (error) {
            if (error instanceof RPCError) {
                this._displayErrorDialog(
                    _t("Payment processing failed"),
                    error.data.message
                );
                this._enableButton();
            } else {
                return Promise.reject(error);
            }
        }
    },

    /**
     * Exchange the typed details for a Zift token.
     *
     * @private
     * @param {Number} paymentOptionId - The id of the selected payment option.
     * @param {String} paymentMethodCode - The code of the selected payment method, if any.
     * @returns {Promise<object>} The token and the fields needed to charge it later.
     */
    async _ziftTokenize(paymentOptionId, paymentMethodCode) {
        const inputs = this._ziftGetInlineFormInputs(
            paymentOptionId,
            paymentMethodCode
        );

        if (paymentMethodCode === "card") {
            const month = String(inputs.month.value).padStart(2, "0");
            const year = String(inputs.year.value).padStart(2, "0").slice(-2);
            const result = await ZiftProxynization.tokenize({
                pan: inputs.card.value.replace(/\D/g, ""),
                expiry: `${month}${year}`,
                csc: inputs.code.value,
                holderName: inputs.holderName.value.trim(),
            });
            return {
                token: result.token,
                accountType: "R",
                // MMYY. Zift requires it on every later charge even when the
                // card is identified by a token, so it travels with it rather
                // than being dropped as display metadata.
                accountAccessory: result.accountAccessory || `${month}${year}`,
                holderName: inputs.holderName.value.trim(),
            };
        }

        const routingNumber = inputs.abaNumber.value.replace(/\D/g, "");
        const result = await ZiftProxynization.tokenizeBankAccount({
            routingNumber: routingNumber,
            accountNumber: inputs.accountNumber.value.replace(/\D/g, ""),
            accountType: inputs.accountType.value,
            holderName: inputs.accountName.value.trim(),
        });
        return {
            token: result.token,
            accountType: result.accountType || inputs.accountType.value,
            // The routing number rides in the same field a card's expiry does.
            accountAccessory: result.routingNumber || routingNumber,
            holderName: inputs.accountName.value.trim(),
        };
    },

    // #=== GETTERS ===#

    /**
     * Return the inline form inputs for the selected payment method.
     *
     * @private
     * @param {Number} paymentOptionId - The id of the selected payment option.
     * @param {String} paymentMethodCode - The code of the selected payment method, if any.
     * @returns {Object} Mapping of input name to DOM element.
     */
    _ziftGetInlineFormInputs(paymentOptionId, paymentMethodCode) {
        const form = this.ziftData[paymentOptionId].form;
        if (paymentMethodCode === "card") {
            return {
                card: form.querySelector("#o_zift_card"),
                month: form.querySelector("#o_zift_month"),
                year: form.querySelector("#o_zift_year"),
                code: form.querySelector("#o_zift_code"),
                holderName: form.querySelector("#o_zift_holder_name"),
            };
        }
        return {
            accountName: form.querySelector("#o_zift_account_name"),
            accountNumber: form.querySelector("#o_zift_account_number"),
            abaNumber: form.querySelector("#o_zift_aba_number"),
            accountType: form.querySelector("#o_zift_account_type"),
        };
    },
});
