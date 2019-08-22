import notify2 , os , random, time
notify2.init('test service')
home_path = '/home/salar'

path = '{}/Pictures/wallpaper/'.format(home_path)

pics = []
for root , directory , files in os.walk(path):
    pics = files

chosen_pic = random.choice(pics)
choice = path + '\"{}\"'.format(chosen_pic)
os.system('wal -i {} &'.format(choice))
os.system('feh --bg-scale {} &'.format(choice))
time.sleep(1.66)
f = open('{}/.cache/wal/conky.conkyrc'.format(home_path),'r')

data = f.read()
while True:
    pos = data.find('#')
    if pos == -1 : break
    data = data[:pos] + '\'' + data[pos+1:pos+7] + '\'' + data[pos+7:]
    
f = open('{}/.cache/wal/conky.conkyrc'.format(home_path),'w')
f.write(data)

n = notify2.Notification('background and colorscheme changed with : {}'.format(chosen_pic))
n.show()
os.system('rm -f {}/.themes/my_openbox/openbox-3/themerc'.format(home_path))
os.system('cp {}/.cache/wal/themerc {}/.themes/my_openbox/openbox-3/themerc'.format(home_path,home_path))
os.system('openbox --reconfigure')
os.system('killall conky')
os.system('killall tint2')
os.system('tint2 -c {}/.cache/wal/tint2.tint2rc &'.format(home_path))
os.system('manjaro-conky-session &')
