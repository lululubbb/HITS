package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

public class CSVRecord_2_5Test {

    private CSVRecord csvRecord;
    private String[] values;
    private Map<String, Integer> mapping;

    @BeforeEach
    public void setUp() throws Exception {
        values = new String[] { "value0", "value1", "value2" };
        mapping = new HashMap<>();
        mapping.put("col0", 0);
        mapping.put("col1", 1);
        mapping.put("col2", 2);

        // Use reflection to access the package-private constructor
        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);
        csvRecord = constructor.newInstance((Object) values, mapping, null, 123L);
    }

    @Test
    @Timeout(8000)
    public void testGetByIndex_ValidIndices() {
        assertEquals("value0", csvRecord.get(0));
        assertEquals("value1", csvRecord.get(1));
        assertEquals("value2", csvRecord.get(2));
    }

    @Test
    @Timeout(8000)
    public void testGetByIndex_IndexOutOfBounds_Negative() {
        assertThrows(ArrayIndexOutOfBoundsException.class, () -> csvRecord.get(-1));
    }

    @Test
    @Timeout(8000)
    public void testGetByIndex_IndexOutOfBounds_TooLarge() {
        assertThrows(ArrayIndexOutOfBoundsException.class, () -> csvRecord.get(values.length));
    }

    @Test
    @Timeout(8000)
    public void testGetPrivateMethodUsingReflection() throws Exception {
        Method getMethod = CSVRecord.class.getDeclaredMethod("get", int.class);
        getMethod.setAccessible(true);
        Object result = getMethod.invoke(csvRecord, 1);
        assertEquals("value1", result);
    }

    @Test
    @Timeout(8000)
    public void testGetWithEmptyValuesArray() throws Exception {
        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);
        CSVRecord emptyRecord = constructor.newInstance((Object) new String[0], Collections.emptyMap(), null, 0L);
        assertThrows(ArrayIndexOutOfBoundsException.class, () -> emptyRecord.get(0));
    }
}