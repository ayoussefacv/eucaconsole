angular.module('AlarmServiceModule', ['EucaRoutes'])
.factory('AlarmService', ['$http', 'eucaRoutes', function ($http, eucaRoutes) {
    $http.defaults.headers.common['X-Requested-With'] = 'XMLHttpRequest';

    return {
        createAlarm: function (alarm, csrf_token) {
            return eucaRoutes.getRouteDeferred('cloudwatch_alarms')
                .then(function (path) {
                    return $http({
                        method: 'PUT',
                        url: path,
                        data: {
                            alarm: alarm,
                            csrf_token: csrf_token
                        }
                    });
                });
        },

        updateAlarm: function (alarm, csrf_token, flash) {
            return eucaRoutes.getRouteDeferred('cloudwatch_alarms')
                .then(function (path) {
                    return $http({
                        method: 'PUT',
                        url: path,
                        data: {
                            alarm: alarm,
                            csrf_token: csrf_token,
                            flash: flash
                        }
                    });
                });
        },

        deleteAlarms: function (alarms, csrf_token, flash) {
            var alarmNames = alarms.map(function (current) {
                return current.name;
            });

            return eucaRoutes.getRouteDeferred('cloudwatch_alarms')
                .then(function (path) {
                    return $http({
                        method: 'DELETE',
                        url: path,
                        data: {
                            alarms: alarmNames,
                            csrf_token: csrf_token,
                            flash: flash
                        }
                    });
                });
        },

        updateActions: function (id, actions) {
            return eucaRoutes.getRouteDeferred('cloudwatch_alarm_actions', { alarm_id: id })
                .then(function (path) {
                    return $http({
                        method: 'PUT',
                        url: path,
                        data: {
                            actions: actions
                        }
                    });
                });
        },

        getHistory: function (id) {
            return eucaRoutes.getRouteDeferred('cloudwatch_alarm_history_json', { alarm_id: id })
                .then(function (path) {
                    return $http({
                        method: 'GET',
                        url: path
                    }).then(function (response) {
                        var data = response.data || {
                            history: []
                        };
                        return data.history;
                    });
                });
        },

        getAlarmsForResource: function (id, type) {
            return eucaRoutes.getRouteDeferred('cloudwatch_alarms_for_resource_json', { id: id })
                .then(function (path) {
                    return $http({
                        method: 'GET',
                        url: path,
                        params: {
                            'resource-type': type
                        }
                    }).then(function success (response) {
                        var data = response.data.results || [];
                        return data;
                    }, function error (response) {
                        return response;
                    });
                });
        }
    };
}]);