这个是存放数学模型的目录
每个py文件是一个数学模型，主函数是。
function_name(symbol,optional_symbol)->str:

将tools分为几类：
1.动量和趋势因子计算
2.价量因子计算
3.波动率因子计算
4.其他因子计算（参考worldquant和专业论文）

数据级别 输入输出

策略部分与指标预测（模型）分开 即信号与执行端分开
执行端直接用大模型本身的决策逻辑
Numbers--Preproccessing-LLM_Analysis-Output(Context)

第一版先预测未来2-4小时的，后续如果有改进可以改变时间窗口 假设最细粒度的输出在"sentiment.db"中是15min(interval列)