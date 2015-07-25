/*
 * Copyright (c) 2013 CoNWeT Lab., Universidad Politécnica de Madrid
 *
 * This file is part of WStore.
 *
 * WStore is free software: you can redistribute it and/or modify
 * it under the terms of the European Union Public Licence (EUPL)
 * as published by the European Commission, either version 1.1
 * of the License, or (at your option) any later version.
 *
 * WStore is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * European Union Public Licence for more details.
 *
 * You should have received a copy of the European Union Public Licence
 * along with WStore.
 * If not, see <https://joinup.ec.europa.eu/software/page/eupl/licence-eupl>.
 */

(function() {

    /**
     * Constructor for the resources binding ModalForm
     * @param offeringElement Offering object used in requests
     * @param vOnly Indicates if the window is in view only mode
     * @returns {BindResourcesForm}
     */
    BindResourcesForm = function BindResourcesForm (offeringElement, vOnly, callerObj) {
        this.viewOnly = vOnly;
        this.offeringElem = offeringElement;
        this.caller = callerObj;
        
    };

    /**
     * BindResourcesForm is a subclass of ModalForm
     */
    BindResourcesForm.prototype = new ModalForm('User resources', '#bind_resources_template');

    BindResourcesForm.prototype.constructor = BindResourcesForm;

    /**
     * Gets the user resources
     */
    BindResourcesForm.prototype.getUserResources = function getUserResources (callback, open) {
        var qstring = '';

        if (open) {
            qstring = '?open=true';
        }
        $.ajax({
            type: "GET",
            url: EndpointManager.getEndpoint('RESOURCE_COLLECTION') + qstring,
            dataType: 'json',
            success: function (response) {
                callback(response);
            },
            error: function (xhr) {
                var resp = xhr.responseText;
                var msg = JSON.parse(resp).message;
                MessageManager.showMessage('Error', msg);
            }
        });
    };

    /**
     * Makes the resource binding request
     * @param resources: Resources to be bound
     */
    BindResourcesForm.prototype.bindResources = function bindResources () {
        var resSelected = [];
        for (var i = 0; i < this.resources.length; i++) {
            if ($('#check-' + i).prop("checked")) {
                resSelected.push({
                    'name': this.resources[i].name,
                    'version': this.resources[i].version
                })
            }
        }
        var csrfToken = $.cookie('csrftoken');
        $.ajax({
            headers: {
                'X-CSRFToken': csrfToken,
            },
            type: "POST",
            url: EndpointManager.getEndpoint('BIND_ENTRY', {
                'organization': this.offeringElem.getOrganization(),
                'name': this.offeringElem.getName(),
                'version': this.offeringElem.getVersion()
            }),
            dataType: 'json',
            contentType: 'application/json',
            data: JSON.stringify(resSelected),
            success: (function (response) {
                MessageManager.showMessage('Bound', 'The resources have been bound');
                this.caller.refreshAndUpdateDetailsView();
            }).bind(this),
            error: function (xhr) {
                var resp = xhr.responseText;
                var msg = JSON.parse(resp).message;
                MessageManager.showMessage('Error', msg);
            }
        });
    };

    /**
     * Implements the method defined in ModalForm
     */
    BindResourcesForm.prototype.includeContents = function includeContents() {
        this.getUserResources(this.paintResources.bind(this), this.offeringElem.isOpen());
    };

    /**
     * Paints the resources
     * @param resources Resources to be painted
     */
    BindResourcesForm.prototype.paintResources = function paintResources (resources) {
        this.resources = resources;

        var labels = {
            'deleted': 'label-important',
            'used': 'label-info',
            'created': ''
        }

        // Check if there is any resource
        if (!resources.length) {
            var msg = "You don't have any resource registered";
            MessageManager.showAlertInfo('No resources', msg, $('.modal-body'));
            $('.alert-info').removeClass('span8');
            return;
        }

        // Append the provider resources
        for (var i = 0; i < resources.length; i++) {
            var res = resources[i];
            var found = false;
            var templ, j = 0;

            res.number = i;
            $.template('resourceTemplate', $('#resource_template'));
            templ = $.tmpl('resourceTemplate', res).
                appendTo('#resources');

            if (!this.viewOnly) {
                // Deleted resources are not displayed in the binding form
                if (res.state == 'deleted') {
                    templ.remove();
                    continue;
                }

                templ.find('.label').remove();
                templ.click(function() {
                    var check = $(this).find('input[type="checkbox"]');
                    if (check.prop('checked')) {
                        check.prop('checked', false);
                    } else {
                        check.prop('checked', true);
                    }
                });
                templ.find('input[type="checkbox"]').click(function(e) {
                    if ($(this).prop('checked')) {
                        $(this).prop('checked', false);
                    } else {
                        $(this).prop('checked', true);
                    }
                });
                // Checks if the resource is already bound to the offering
                offeringRes = this.offeringElem.getResources()
                while(!found && j < offeringRes.length) {
                    if (res.name == offeringRes[j].name && res.version == offeringRes[j].version) {
                        found = true;
                        $('#check-' + i).prop('checked', true);
                    }
                    j++;
                }
            } else {
                // In the visualization mode it should be possible to expand resource info
                templ.find('.label').addClass(labels[res.state]);
                templ.click(function (self, resource) {
                    var resDetails = new ResourceDetailsPainter(resource, self);
                    return function () {
                        resDetails.paint();
                    }
                }(this, res));
            }
        }

        if(!this.viewOnly) {
            // Set listener
            $('.modal-footer > .btn').click((function () {
                this.bindResources();
            }).bind(this));
        } else {
            $('[type="checkbox"]').remove();
        }
    };

})();

(function() {

    /**
     * Constructor of the ResourceDeatilsPainter
     * @param resource. Object containing the info of the resource to be displayed
     * @param caller. BindResources object that called the view used to return when needed
     * @returns {ResourceDetailsPainter}
     */
    ResourceDetailsPainter = function ResourceDetailsPainter(resource, caller) {
        this.resource = resource;
        this.caller = caller;
    };

    /**
     * Private method that hides the current modal
     */
    var hideModal = function hideModal() {
        // Hide the current modal
        $('#message').off('hidden');
        $('#message').modal('hide');

        //  Build a container for the new message
        $('<div id="new-container"></div>').appendTo('#message-container');
    }

    /**
     * Private method that shows the hidden modal
     */
    ResourceDetailsPainter.prototype.showModal = function showModal() {
        closeHandler();
        this.caller.display();
    }

    /**
     * Handler for removing the resource
     */
    var removeHandler = function removeHandler() {
        var resCllient;
        // Hide yes no window
        $('#sec-message').modal('hide');
        $('#new-container').remove();

        // Create a resource client
        resClient = new ServerClient('RESOURCE_ENTRY', '');
        resClient.remove(this.showModal.bind(this), {
            'provider': ORGANIZATION,
            'name': this.resource.name,
            'version': this.resource.version
        });
    };

    /**
     * Handler for the cancel option when removing the resource.
     * Redisplays the details view modal
     */
    var closeHandler = function closeHandler() {
        // Hide yes no window
        $('#sec-message').modal('hide');
        $('#new-container').remove();

        // Restore resource view and hidden listener
        $('#message').modal('show');
        $('#message').on('hidden', function(){
            $('#message-container').empty();
        });
    };

    /**
     * Set the different listeners included in the resource details
     * view, including the back button, the edit button and the remove
     * button
     */
    ResourceDetailsPainter.prototype.setListeners = function setListeners () {
        // Set back listener
        $('#res-back').click(function() {
            this.caller.display();
        }.bind(this));

        if (this.resource.state != 'deleted') {
            // Set delete listener
            $('.res-remove').click(function() {
                var msg = "Are you sure that you want to remove the resource " + this.resource.name + ' version ' + this.resource.version;

                hideModal();

                // Show yes no window
                MessageManager.showYesNoWindow(msg, removeHandler.bind(this), 'Remove', $('#new-container'), closeHandler.bind(this));
            }.bind(this));

            // Set update listener
            $('.res-edit').click(function() {
                var regRes;

                hideModal();

                // Create the new form
                regRes = buildRegisterResourceForm('edit', this.resource, '#sec-message', this);
                regRes.display($('#new-container'));

                // Override hidden behaviour
                $('#sec-message').off('hidden');
                $('#sec-message').on('hidden', this.showModal.bind(this));
            }.bind(this));

            // Set upgade listener
            $('.res-upgrade').click(function() {
                var regRes;

                hideModal();
                // Create the new form
                regRes = buildRegisterResourceForm('upgrade', this.resource, '#sec-message', this);
                regRes.display($('#new-container'));

                // Override hidden behaviour
                $('#sec-message').off('hidden');
                $('#sec-message').on('hidden', this.showModal.bind(this));
            }.bind(this));
        }
    };

    /**
     * Paint the resource details in the displayed modal
     */
    ResourceDetailsPainter.prototype.paint = function paint() {
        // Clean modal body
        $('.modal-body').empty()

        $.template('resourceDetails', $('#resource_details_template'));
        $.tmpl('resourceDetails', this.resource).appendTo('.modal-body');

        // If the resource is deleted remove options
        if (this.resource.state == 'deleted') {
            $('.res-remove').addClass('hide');
            $('.res-edit').addClass('hide');
            $('.res-upgrade').addClass('hide');
        }
        this.setListeners();
    };
})();
