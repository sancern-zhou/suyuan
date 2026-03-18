天机API概览
本文档为天机API接口调用试用规范，为第三方开发和测试提供参考。如本文档有遗漏或者不能满足您的需求，请联系运营人员进行反馈。

接口设计
本文档定义了第三方开发和测试提供API调用方式 ，目前支持大气要素: 100米风速和风向、10米风速和风向、2米温度、降雨量、2米湿度、辐照度、总云量、低云量等相关单点数据查询。

资源权限
本结构根据平台用户名和密码做权限认定，第三方平台需获取到授权该平台的APIKey，才可正常调用API，请联系天机运营人员进行授权。

支持协议
接口均使用https协议进行访问，确保数据加密传输。

认证机制
采用基于key的用户认证机制，用户调用接口前需要先获取APIKey，在调用其他所有接口时需要携带APIKey参数。

返回结果
这里的返回结果专指在HTTP响应的状态码（Status Code）为200时的响应信息。

所有返回结果默认均使用JSON格式，接口中定义的对象都将转换为JSON格式，字符编码格式为UTF-8。HTTP响应头设置Content-Type:application/json;charset=UTF-8。 对于文件下载以及流请求，返回的是数据流

标准正确格式为：{"code":200,"message":"成功","data":Json对象或列表}；

标准错误格式为：{"code":非200,"message":"xxx","data":""}；

其中code为错误码，message为错误信息，data为返回值，格式为JSON对象、列表或字符串。

错误处理
首先需要判断HTTP响应的状态码（Status Code），如果为404、500等状态，则按照浏览器等常用HTTP客户端的惯例处理。

返回状态码为200时，表示服务器处理正常，此时再判断返回结果，根据具体接口的返回值中的错误码code进行处理，具体请参考各接口的错误码说明。

如果返回结果与上节描述的格式不一致，即非JSON格式，应以错误处理。如果返回结果的对象中缺少某个属性，则应以该属性的值为空串处理。

JSON格式返回
1.接口说明
正式接口路径： https://api.tjweather.com

试用接口路径： https://api.tjweather.com/beta

当前版本： v1.0.0

请求方式： GET

返回类型： JSON

请求数据类型：

接口描述： 查询单点坐标最新的气象高精度预报数据，范围全球可选，预报时长可选，时间分辨率提供15分钟、1小时选项，返回JSON类型数据。

2.请求参数
参数名	说明	参数类型	默认值	必填	备注
key	您的私钥	字符串	无	是	暂时线下交付
loc	位置	字符串	无	是	支持全球范围任意经纬度查询，经度范围[-180,180]或[0,360]，纬度范围[-90,90]格式：经度在前纬度在后，按照“,“分隔，分隔符支持中文和英文。举例：116.23128,40.22077
t_res	时间分辨率	字符串	1h	否	支持查询时间分辨率为15分钟(格式：15min)、1小时(格式：1h)的数据，缺省为1h
fcst_days	预报天数	整数	3	否	支持选择未来D天的不同预报长度的预报数据，D>=0，支持总时长5、10、15、30、45天内数据
fcst_hours	预报小时数	整数	0	否	支持选择未来H小时的不同预报长度的预报数据，H>=0，缺省为0
fields	要素	字符串	ws100m	否	支持要素请参照要素编码列表，缺省为百米风，按照“,“分隔，举例：ws100m,ws10m,t2m
tz	时区	整数	8	否	缺省为北京时，8，范围[-12,12]
grid	格点数据类型	字符串	1	否	缺省为:"1"，格点数据支持，"1","3","5","7"
注：总预报时长按照 tot_hrs = fcst_days*24+fcst_hours 计算。

3.支持要素编码列表
3.1 支持全球区域要素(经度范围[-180,180]或[0,360]，纬度范围[-90,90])
要素	描述	单位	支持天数
u10m	十米U风速	m/s	10/15/30/45
v10m	十米V风速	m/s	10/15/30/45
ws10m	十米风速	m/s	10/15/30/45
wd10m	十米风向	°	10/15/30/45
u100m	百米U风速	m/s	10/15/30/45
v100m	百米V风速	m/s	10/15/30/45
wd100m	百米风向	°	10/15/30/45
ws100m	百米风速	m/s	10/15/30/45
t2m	2米温度	°C	10/15/30/45
cldt	总云量	1	10/15/30/45
cldl	低云量	1	10/15/30
psz	地表气压	Pa	10/15/30/45
rh2m	2米相对湿度	%	10/15/30/45
tp	降水	mm/hr	10/15/30/45
pres	降雪量	mm	10/15/30/45
prer	累积降水	mm	10/15/30/45
dod	沙尘光学厚度		10/15/30
dust_conc	地表沙尘浓度	μg/m³	10/15/30
dust_ddep	累计沉降	mg/m²	10/15/30
TMPsfc	地表气温	K	10/15/30
DLWRFsfc	地表向下长波通量	W/㎡	10/15/30
ssrd	辐照度	W/㎡	10/15/30/45
ddsf_ave	散辐射	W/㎡	10/15
bdsf_ave	直辐射	W/㎡	10/15
SOILT1	0-10cm土壤温度	K	10
SOILT2	10-40cm土壤温度	K	10
SOILT3	40-100cm土壤温度	K	10
SOILT4	100-200cm土壤温度	K	10
prei	累积降冰	mm	10
preg	累积霰降水	mm	10
dpt2m	2米露点温度	K	10
gust	阵风	m/s	10
cape	对流有效位能	J/kg	10
u1000	1000hPa纬向风	m/s	10
u925	925hPa纬向风	m/s	10
u850	850hPa纬向风	m/s	10
u800	800hPa纬向风	m/s	10
u700	700hPa纬向风	m/s	10
u600	600hPa纬向风	m/s	10
u500	500hPa纬向风	m/s	10
u400	400hPa纬向风	m/s	10
u300	300hPa纬向风	m/s	10
u200	200hPa纬向风	m/s	10
u100	100hPa纬向风	m/s	10
v1000	1000hPa经向风	m/s	10
v925	925hPa经向风	m/s	10
v850	850hPa经向风	m/s	10
v800	800hPa经向风	m/s	10
v700	700hPa经向风	m/s	10
v600	600hPa经向风	m/s	10
v500	500hPa经向风	m/s	10
v400	400hPa经向风	m/s	10
v300	300hPa经向风	m/s	10
v200	200hPa经向风	m/s	10
v100	100hPa经向风	m/s	10
t1000	1000hPa温度	K	10
t925	925hPa温度	K	10
t850	850hPa温度	K	10
t800	800hPa温度	K	10
t700	700hPa温度	K	10
t600	600hPa温度	K	10
t500	500hPa温度	K	10
t400	400hPa温度	K	10
t300	300hPa温度	K	10
t200	200hPa温度	K	10
t100	100hPa温度	K	10
q1000	1000hPa比湿	kg/kg	10
q925	925hPa比湿	kg/kg	10
q850	850hPa比湿	kg/kg	10
q800	800hPa比湿	kg/kg	10
q700	700hPa比湿	kg/kg	10
q600	600hPa比湿	kg/kg	10
q500	500hPa比湿	kg/kg	10
q400	400hPa比湿	kg/kg	10
q300	300hPa比湿	kg/kg	10
q200	200hPa比湿	kg/kg	10
q100	100hPa比湿	kg/kg	10
SPFH2m	2米比湿	kg/kg	10
rh1000	1000hPa相对湿度	%	10
rh925	925hPa相对湿度	%	10
rh850	850hPa相对湿度	%	10
rh800	800hPa相对湿度	%	10
rh700	700hPa相对湿度	%	10
rh600	600hPa相对湿度	%	10
rh500	500hPa相对湿度	%	10
rh400	400hPa相对湿度	%	10
rh300	300hPa相对湿度	%	10
rh200	200hPa相对湿度	%	10
rh100	100hPa相对湿度	%	10
h1000	1000hPa位势高度	m	10
h925	925hPa位势高度	m	10
h850	850hPa位势高度	m	10
h800	800hPa位势高度	m	10
h700	700hPa位势高度	m	10
h600	600hPa位势高度	m	10
h500	500hPa位势高度	m	10
h400	400hPa位势高度	m	10
h300	300hPa位势高度	m	10
h200	200hPa位势高度	m	10
h100	100hPa位势高度	m	10
omg1000	1000hPa垂直速度	Pa/s	10
omg925	925hPa垂直速度	Pa/s	10
omg850	850hPa垂直速度	Pa/s	10
omg800	800hPa垂直速度	Pa/s	10
omg700	700hPa垂直速度	Pa/s	10
omg600	600hPa垂直速度	Pa/s	10
omg500	500hPa垂直速度	Pa/s	10
omg400	400hPa垂直速度	Pa/s	10
omg300	300hPa垂直速度	Pa/s	10
omg200	200hPa垂直速度	Pa/s	10
omg100	100hPa垂直速度	Pa/s	10
dp1000	1000hPa露点温度	K	10
dp925	925hPa露点温度	K	10
dp850	850hPa露点温度	K	10
dp800	800hPa露点温度	K	10
dp700	700hPa露点温度	K	10
dp600	600hPa露点温度	K	10
dp500	500hPa露点温度	K	10
dp400	400hPa露点温度	K	10
dp300	300hPa露点温度	K	10
dp200	200hPa露点温度	K	10
dp100	100hPa露点温度	K	10
slp	海平面气压	mb	10/15/30
base_reflectivity	基本反射率	dBz	10
max_reflectivity	明日雷达	dBz	10
SHTFLsfc	地表感热通量	W/m²	10
LHTFLsfc	地表潜热通量	W/m²	10
ZORLsfc	地表粗糙度	m	10
qnh	海平面修正气压	hPa	10
t70m	70米温度	K	10
USWRFsfc	地表向上短波通量	W/㎡	10
3.2 只支持中国区域要素(经度范围[50.5,149.95]，纬度范围[0.05,69.95])
要素	描述	单位	支持天数
u30m	30米纬向风	m/s	10/15/30/45
u50m	50米纬向风	m/s	10/15/30
u60m	60米纬向风	m/s	10
u65m	65米纬向风	m/s	10
u70m	70米纬向风	m/s	10
u75m	75米纬向风	m/s	10
u80m	80米纬向风	m/s	10
u85m	85米纬向风	m/s	10
u90m	90米纬向风	m/s	10
u95m	95米纬向风	m/s	10
u105m	105米纬向风	m/s	10
u110m	110米纬向风	m/s	10
u115m	115米纬向风	m/s	10
u120m	120米纬向风	m/s	10
u125m	125米纬向风	m/s	10
u130m	130米纬向风	m/s	10
u135m	135米纬向风	m/s	10
u140m	140米纬向风	m/s	10
u145m	145米纬向风	m/s	10
u150m	150米纬向风	m/s	10
u160m	160米纬向风	m/s	10
u170m	170米纬向风	m/s	10/15/30
v30m	30米经向风	m/s	10/15/30/45
v50m	50米经向风	m/s	10/15/30
v60m	60米经向风	m/s	10
v65m	65米经向风	m/s	10
v70m	70米经向风	m/s	10
v75m	75米经向风	m/s	10
v80m	80米经向风	m/s	10
v85m	85米经向风	m/s	10
v90m	90米经向风	m/s	10
v95m	95米经向风	m/s	10
v105m	105米经向风	m/s	10
v110m	110米经向风	m/s	10
v115m	115米经向风	m/s	10
v120m	120米经向风	m/s	10
v125m	125米经向风	m/s	10
v130m	130米经向风	m/s	10
v135m	135米经向风	m/s	10
v140m	140米经向风	m/s	10
v145m	145米经向风	m/s	10
v150m	150米经向风	m/s	10
v160m	160米经向风	m/s	10
v170m	170米经向风	m/s	10/15/30
ws30m	30米风速	m/s	10/15/30/45
ws50m	50米风速	m/s	10/15/30
ws60m	60米风速	m/s	10
ws65m	65米风速	m/s	10
ws70m	70米风速	m/s	10
ws75m	75米风速	m/s	10
ws80m	80米风速	m/s	10
ws85m	85米风速	m/s	10
ws90m	90米风速	m/s	10
ws95m	95米风速	m/s	10
ws105m	105米风速	m/s	10
ws110m	110米风速	m/s	10
ws115m	115米风速	m/s	10
ws120m	120米风速	m/s	10
ws125m	125米风速	m/s	10
ws130m	130米风速	m/s	10
ws135m	135米风速	m/s	10
ws140m	140米风速	m/s	10
ws145m	145米风速	m/s	10
ws150m	150米风速	m/s	10
ws160m	160米风速	m/s	10
ws170m	170米风速	m/s	10/15/30
wd30m	30米风向	°	10/15/30/45
wd50m	50米风向	°	10/15/30
wd60m	60米风向	°	10
wd65m	65米风向	°	10
wd70m	70米风向	°	10
wd75m	75米风向	°	10
wd80m	80米风向	°	10
wd85m	85米风向	°	10
wd90m	90米风向	°	10
wd95m	95米风向	°	10
wd105m	105米风向	°	10
wd110m	110米风向	°	10
wd115m	115米风向	°	10
wd120m	120米风向	°	10
wd125m	125米风向	°	10
wd130m	130米风向	°	10
wd135m	135米风向	°	10
wd140m	140米风向	°	10
wd145m	145米风向	°	10
wd150m	150米风向	°	10
wd160m	160米风向	°	10
wd170m	170米风向	°	10/15/30
4.请求示例
cURL请求示例


curl -l 'https://api.tjweather.com/beta?key=APPxxxx&fields=ws100m&loc=99.58,36.44&fcst_days=0&fcst_hours=2'
Java请求示例


import okhttp3.*;

public class QueryClusterInfoDemo {

    public static final String URL = "https://api.tjweather.com/beta?key=APPxxxx&fields=ws100m&loc=99.58,36.44&fcst_days=0&fcst_hours=2";

    public static void main(String[] args) throws Exception {
        OkHttpClient client = new OkHttpClient().newBuilder()
                .build();
        Request request = new Request.Builder()
                .url(URL)
                .method("GET", null)
                .build();
        Response response = client.newCall(request).execute();
        System.out.println(response.body().string());
    }
}
支持重试示例
当客户端出现信号灯超时，服务器拒绝等异常情况请求失败时，可以通过重试提升成功率


import okhttp3.*;

public class QueryClusterInfoDemo {
    public static final String URL = "https://api.tjweather.com/beta?key=APPxxxx&fields=ws100m&loc=99.58,36.44&fcst_days=0&fcst_hours=2";
    
    public static Request buildOkHttpRequest(String url) {
        return new Request.Builder()
                .url(url)
                .method("GET", null)
                .build();
    }

    public static void main(String[] args) {
        OkHttpClient client = new OkHttpClient().newBuilder().build();
        Request request = buildOkHttpRequest(URL);
        int retryCount = 0;
        int maxRetries = 3;
        boolean success = false;
        while (retryCount < maxRetries && !success) {
            try {
                Response response = client.newCall(request).execute();
                success = true;
                System.out.println(response.body().string());
            } catch (Exception e) {
                retryCount++;
            }
        }
        if (!success) {
            System.out.println("Failed to complete the request after " + maxRetries + " retries.");
        }
    }
}
5.响应消息
返回参数：

参数名	参数类型	备注	示例
code	状态码	200为成功	200
message	状态描述		成功
data	数据	对象	
_.data	要素数据	列表	
_._.time	预报时间		2024-01-03T21:00+08:00
_._.field	要素数据	field为对应要素	ws100m
_.units	单位		
_._.field	该要素单位	field为对应要素	"ws100m": "m/s"
_.time_init	起报时间	北京时间08时或20时	2024-01-03T20:00+08:00
返回示例：


{
  "code": 200,
  "message": "成功",
  "data": {
    "units": {
      "ws100m": "m/s"
    },
    "data": [
      {
        "time": "2024-01-03T21:00+08:00",
        "ws100m": 3.7788534
      },
      {
        "time": "2024-01-03T22:00+08:00",
        "ws100m": 3.3296072
      }
    ],
    "time_init": "2024-01-03T20:00+08:00"
  }
}
错误示例：


{
  "code": 10001,
  "message": "查询失败，请稍后再试！",
  "data": null
}
6.常见错误码
错误码	说明
500	服务器内部错误
10001	查询失败，请稍后再试
10004	接口不存在
10005	超过访问量上限(N次/日)
10006	要素超出可查询有效期
10007	超过并发量上限(N次/秒)
10011	请求链接与所用的appKey不对应，请确认使用的是正式链接或是试用链接
10012	非法appKey！
10014	服务繁忙，请稍后再访问！
10017	用户状态异常
20001	缺失必选参数
20002	要素暂未开放
20003	要素未订阅
20004	参数值非法，例如参数要求是数字，结果输入中文
20005	参数格式非法，例如坐标分隔符需要用逗号分隔，使用了其他非法字符进行分割
20006	参数长度非法，输入超过长度限制
20007	经度不在[-180,360]范围内
20008	纬度不在[90,-90]范围内
20009	当前请求预报数据最多查询N天！
20010	目前仅提供15min/1h时间分辨率预报数据！
20011	当前请求同时最多获取N个要素预报数据！
20012	格点数据非法，目前仅支持1,3,5,7！
20014	用户API未启用
20015	API未启用
20017	当前请求点位坐标loc未订阅！
当前请求点位坐标grid未订阅！
滚蛋