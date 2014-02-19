/**
 * @fileOverview IAM Policy Wizard JS
 * @requires AngularJS
 *
 */

angular.module('IAMPolicyWizard', [])
    .controller('IAMPolicyWizardCtrl', function ($scope, $http, $timeout) {
        $scope.wizardForm = $('#iam-policy-form');
        $scope.policyGenerator = $('#policy-generator');
        $scope.policyJsonEndpoint = '';
        $scope.policyTextarea = document.getElementById('policy');
        $scope.codeEditor = null;
        $scope.policyStatements = [];
        $scope.addedStatements = [];
        $scope.policyAPIVersion = "2012-10-17";
        $scope.initController = function (policyJsonEndpoint) {
            $scope.policyJsonEndpoint = policyJsonEndpoint;
            $scope.initCodeMirror();
        };
        $scope.initCodeMirror = function () {
            $scope.codeEditor = CodeMirror.fromTextArea($scope.policyTextarea, {
                mode: "javascript",
                lineWrapping: true,
                styleActiveLine: true,
                lineNumbers: true
            });
        };
        $scope.visitStep = function(step) {
            $('#tabStep' + step).click();
        };
        $scope.setPolicyName = function (policyType) {
            var typeNameMapping = {
                'admin_access': 'AccountAdminAccessPolicy',
                'user_access': 'PowerUserAccessPolicy',
                'monitor_access': 'ReadOnlyUserAccessPolicy',
                'blank': 'CustomAccessPolicy'
            }
            $scope.policyName = typeNameMapping[policyType] || '';
        };
        $scope.selectPolicy = function(policyType) {
            // Fetch hard-coded canned policies
            var jsonUrl = $scope.policyJsonEndpoint + "?type=" + policyType;
            $http.get(jsonUrl).success(function(oData) {
                var results = oData ? oData['policy'] : '',
                    formattedResults = '';
                if (results) {
                    formattedResults = JSON.stringify(results, null, 2);
                    $scope.policyText = formattedResults;
                    $scope.codeEditor.setValue(formattedResults);
                    $scope.codeEditor.focus();
                }
            });
            // Set policy name
            $scope.setPolicyName(policyType);
        };
        $scope.updatePolicy = function() {
            var generatorPolicy = { "Version": $scope.policyAPIVersion, "Statement": $scope.policyStatements };
            var formattedResults = JSON.stringify(generatorPolicy, null, 2);
            if ($scope.policyStatements.length) {
                $scope.policyText = formattedResults;
                $scope.codeEditor.setValue(formattedResults);
            }
        };
        $scope.updateStatements = function () {
            $scope.policyStatements = [];
            $scope.policyGenerator.find('.action').find('i.selected').each(function(idx, item) {
                var namespace = item.getAttribute('data-namespace'),
                    action = item.getAttribute('data-action'),
                    effect = item.getAttribute('data-effect'),
                    nsAction = namespace.toLowerCase() + ':' + action,
                    resource = $(item).closest('tr').find('.resource').val() || '*';
                $scope.policyStatements.push({
                    "Action": [nsAction],
                    "Resource": resource,
                    "Effect": effect
                });
            });
            $scope.updatePolicy();
        };
        $scope.handleSelection = function ($event) {
            var tgt = $($event.target);
            tgt.closest('tr').find('i').removeClass('selected');
            tgt.addClass('selected');
            $timeout(function () {
                $scope.updateStatements();
            }, 50);
        };
        $scope.toggleAll = function (action, namespace, $event) {
            // action is 'allow' or 'deny'
            var nsSelector = '.' + namespace,
                enabledMark = action === 'allow' ? '.fi-check' : '.fi-x',
                disabledMark = action === 'allow' ? '.fi-x' : '.fi-check';
            $($event.target).addClass('selected');
            $scope.policyGenerator.find(nsSelector).find(enabledMark).addClass('selected');
            $scope.policyGenerator.find(nsSelector).find(disabledMark).removeClass('selected');
            $timeout(function () {
                $scope.updateStatements();
            }, 100)
        };
        $scope.toggleAdvanced = function ($event) {
            $($event.target).closest('tr').find('.advanced').toggleClass('hide');
        };
    })
;

