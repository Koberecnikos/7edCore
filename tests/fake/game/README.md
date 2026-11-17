Tiny stand-ins for the game's Assembly-CSharp.dll (two "versions") and a code mod that uses it,
for the mod compatibility check tests. Built with Mono:

    (each built as Assembly-CSharp.dll in its own folder, then renamed)
    cat Game.cs ModApi.cs > a.cs;  mcs -target:library -out:Assembly-CSharp.dll a.cs      -> Assembly-CSharp-3.4.dll
    sed -e 's/public interface ITileEntityLootable { }//; s/ public int fuel;//' Game.cs > a.cs; cat ModApi.cs >> a.cs
    mcs -target:library -out:Assembly-CSharp.dll a.cs                                   -> Assembly-CSharp-3.5.dll
    mcs -target:library -out:0Harmony.dll Harm.cs      (stand-in for the game's Mods/0_TFP_Harmony/0Harmony.dll)
    mcs -target:library -r:Assembly-CSharp-3.4.dll -r:0Harmony.dll -out:TestCodeMod.dll Mod.cs
    cat Game.cs ModApi.cs > /tmp/x/GameApi.cs; mcs -target:library -out:/tmp/x/Assembly-CSharp.dll /tmp/x/GameApi.cs
    mcs -target:library -r:/tmp/x/Assembly-CSharp.dll -out:GatedMod.dll Gated.cs   # a mod that refuses unknown game versions
