/** @odoo-module */

import { registry } from "@web/core/registry";
import { formView } from "@web/views/form/form_view";

const patchIframePreview = {
    setup() {
        this._super(...arguments);
        // nada extra aquí
    },
    onWillStart() {
        if (super.onWillStart) return super.onWillStart(...arguments);
    },
    onMounted() {
        if (super.onMounted) super.onMounted(...arguments);
        this._setIframeSrc();
    },
    onWillUpdateProps(nextProps) {
        if (super.onWillUpdateProps) super.onWillUpdateProps(nextProps);
        // cuando cambian props (por ejemplo, cambia pdf_file/pdf_preview_url), reintenta setear
        queueMicrotask(() => this._setIframeSrc());
    },
    _setIframeSrc() {
        try {
            const iframe = this.el.querySelector("iframe.bhe_pdf_iframe");
            if (!iframe) return;
            const record = this.props && this.props.record;
            // En OWL form renderer, valores accesibles en record.data
            const url = record && record.data && record.data.pdf_preview_url;
            if (url && iframe.getAttribute("src") !== url) {
                iframe.setAttribute("src", url);
            }
        } catch (e) {
            // silencioso
            // console.warn("bhe iframe set error", e);
        }
    },
};

// Registrar un patch de la vista form por modelo específico
registry.category("views").add("boleta_honorarios_form_with_iframe", {
    ...formView,
    Controller: class extends formView.Controller {
        setup() {
            super.setup();
            Object.assign(this, patchIframePreview);
            if (this.onMounted) this.onMounted = patchIframePreview.onMounted.bind(this);
            if (this.onWillUpdateProps) this.onWillUpdateProps = patchIframePreview.onWillUpdateProps.bind(this);
            this._setIframeSrc = patchIframePreview._setIframeSrc.bind(this);
        }
    },
});