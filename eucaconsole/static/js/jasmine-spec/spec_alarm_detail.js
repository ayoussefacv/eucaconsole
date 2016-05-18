describe('AlarmDetailPage', function () {
    
    beforeEach(angular.mock.module('AlarmDetailPage'));

    var scope, controller;
    var templateData = {
        alarm_json: JSON.stringify({
            "comparison": ">=",
            "alarm_actions": [
                "arn:aws:autoscaling::000753323549:scalingPolicy:a3c937ff-0edd-4958-93f8-568366f4b2b7:autoScalingGroupName/dakv2-ConsoleScalingGroup-7YHDNGPNSTRSF:policyName/AdamTest"
            ],
            "ok_actions": [
                "arn:aws:autoscaling::000753323549:scalingPolicy:a3c937ff-0edd-4958-93f8-568366f4b2b7:autoScalingGroupName/dakv2-ConsoleScalingGroup-7YHDNGPNSTRSF:policyName/AdamTest"
            ],
            "name": "AWS/EC2 -  - CPUUtilization",
            "evaluation_periods": 3,
            "metric": "CPUUtilization",
            "description": "{{ 1 + 3 }}",
            "namespace": "AWS/EC2",
            "period": 900,
            "actions": [
                {
                    "autoscaling_group_name": "dakv2-ConsoleScalingGroup-7YHDNGPNSTRSF",
                    "alarm_state": "ALARM",
                    "arn": "arn:aws:autoscaling::000753323549:scalingPolicy:a3c937ff-0edd-4958-93f8-568366f4b2b7:autoScalingGroupName/dakv2-ConsoleScalingGroup-7YHDNGPNSTRSF:policyName/AdamTest",
                    "policy_name": "AdamTest"
                }, {
                    "autoscaling_group_name": "dakv2-ConsoleScalingGroup-7YHDNGPNSTRSF",
                    "alarm_state": "INSUFFICIENT_DATA",
                    "arn": "arn:aws:autoscaling::000753323549:scalingPolicy:a3c937ff-0edd-4958-93f8-568366f4b2b7:autoScalingGroupName/dakv2-ConsoleScalingGroup-7YHDNGPNSTRSF:policyName/AdamTest",
                    "policy_name": "AdamTest"
                }, {
                    "autoscaling_group_name": "dakv2-ConsoleScalingGroup-7YHDNGPNSTRSF",
                    "alarm_state": "OK",
                    "arn": "arn:aws:autoscaling::000753323549:scalingPolicy:a3c937ff-0edd-4958-93f8-568366f4b2b7:autoScalingGroupName/dakv2-ConsoleScalingGroup-7YHDNGPNSTRSF:policyName/AdamTest",
                    "policy_name": "AdamTest"
                }
            ],
            "threshold": 35.0,
            "state": "INSUFFICIENT_DATA",
            "insufficient_data_actions": [
                "arn:aws:autoscaling::000753323549:scalingPolicy:a3c937ff-0edd-4958-93f8-568366f4b2b7:autoScalingGroupName/dakv2-ConsoleScalingGroup-7YHDNGPNSTRSF:policyName/AdamTest"
            ],
            "statistic": "Sum",
            "stateReason": "Unchecked: Initial alarm creation",
            "unit": "None",
            "dimensions": {
                "InstanceId": ["i-1fa6b766"],
                "AutoScalingGroupName": ["dakv2-ConsoleScalingGroup-7YHDNGPNSTRSF"]
            }
        }).replace(/"/g, '&quot;')
    };

    beforeEach(angular.mock.inject(function ($rootScope, $compile) {
        scope = $rootScope.$new();
        var tmplSrc = window.__html__['templates/cloudwatch/alarms_detail.pt'];
        tmplSrc = tmplSrc.replace(/\$\{([_a-zA-Z]+)\}/g, function (match, key) {
            if(key in templateData) {
                return templateData[key];
            }
            return match;
        });
        var element = angular.element(tmplSrc);

        var template = $compile(element)(scope);
        scope.$digest();

        controller = element.controller;
    }));

    it('should blah', function () {
    });
});
